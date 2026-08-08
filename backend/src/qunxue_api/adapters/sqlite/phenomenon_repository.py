import json
from dataclasses import replace
from datetime import UTC, datetime
from hashlib import sha256
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from qunxue_api.adapters.sqlite import (
    MaterialIntakeRunRow,
    PhenomenonCandidateVersionRow,
    PhenomenonExampleRow,
    PhenomenonStateRow,
    ResearchTaskRow,
)
from qunxue_api.modules.research_intake import (
    ConfirmedPhenomenonSnapshot,
    DirectPhenomenonInput,
    MaterialIntakeRun,
    PhenomenonCandidate,
    PhenomenonCandidateDraft,
    PhenomenonCandidateStatus,
    PhenomenonEvidenceRefSnapshot,
    PhenomenonEvidenceVerificationStatus,
    PhenomenonExample,
    PhenomenonModelSnapshot,
    PhenomenonProgress,
    PhenomenonRepository,
    PreparedPhenomenonCandidate,
)


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class SqlitePhenomenonRepository(PhenomenonRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_examples(self) -> list[PhenomenonExample]:
        rows = self._session.scalars(
            select(PhenomenonExampleRow).order_by(PhenomenonExampleRow.position)
        )
        return [
            PhenomenonExample(
                example_id=row.example_id,
                title=row.title,
                phenomenon=row.phenomenon,
                research_intent=row.research_intent,
                context=row.context,
            )
            for row in rows
        ]

    def submit_material(
        self,
        *,
        run_id: UUID,
        task_id: UUID,
        idempotency_key: str,
        filename: str,
        media_type: str,
        processing_policy_version: str,
        candidates: tuple[PreparedPhenomenonCandidate, ...],
        model: PhenomenonModelSnapshot,
        now: datetime,
    ) -> MaterialIntakeRun:
        existing = self._session.scalar(
            select(MaterialIntakeRunRow).where(
                MaterialIntakeRunRow.task_id == str(task_id),
                MaterialIntakeRunRow.idempotency_key == idempotency_key,
            )
        )
        if existing is not None:
            return self._to_material_run(existing)

        material_candidates = tuple(
            PhenomenonCandidate(
                candidate_id=item.candidate_id,
                task_id=task_id,
                version=1,
                status=PhenomenonCandidateStatus.PROPOSED,
                phenomenon=item.draft.phenomenon,
                research_intent=item.draft.research_intent,
                context=item.draft.context,
                source_ref_ids=item.draft.source_ref_ids,
                evidence_refs=item.evidence_refs,
                model=model,
                missing_information=item.missing_information,
                source_traceability="traceable",
                content_origin="system_generated",
            )
            for item in candidates
        )
        for candidate in material_candidates:
            self._append_candidate(candidate, now=now)

        self._session.add(
            MaterialIntakeRunRow(
                run_id=str(run_id),
                task_id=str(task_id),
                idempotency_key=idempotency_key,
                status="completed",
                filename=filename,
                media_type=media_type,
                processing_policy_version=processing_policy_version,
                candidate_ids=[str(item.candidate_id) for item in material_candidates],
                accepted_at=now,
            )
        )
        first = material_candidates[0]
        self._session.add(
            PhenomenonStateRow(
                task_id=str(task_id),
                input_id=str(run_id),
                input_version=1,
                candidate_id=str(first.candidate_id),
                candidate_version=first.version,
                candidate_status=first.status.value,
                phenomenon=first.phenomenon,
                research_intent=first.research_intent,
                context=first.context,
                source_ref_ids=list(first.source_ref_ids),
                evidence_refs=[
                    self._evidence_to_json(item) for item in first.evidence_refs
                ],
                missing_information=list(first.missing_information),
                source_traceability=first.source_traceability,
                content_origin=first.content_origin,
                model_provider=model.provider,
                model_version=model.model_version,
                model_capability=model.capability,
                model_degraded=model.degraded,
                knowledge_release_id=model.knowledge_release_id,
                trace_id=str(model.trace_id),
                request_id=str(model.request_id),
                contract_version=model.contract_version,
                phenomenon_query_id=None,
                content_hash=None,
                confirmed_at=None,
                accepted_at=now,
            )
        )
        self._session.flush()
        persisted = self._session.get(MaterialIntakeRunRow, str(run_id))
        assert persisted is not None
        return self._to_material_run(persisted)

    def get_material_run(
        self,
        run_id: UUID,
        user_id: UUID,
    ) -> MaterialIntakeRun | None:
        row = self._session.scalar(
            select(MaterialIntakeRunRow)
            .join(ResearchTaskRow, ResearchTaskRow.task_id == MaterialIntakeRunRow.task_id)
            .where(
                MaterialIntakeRunRow.run_id == str(run_id),
                ResearchTaskRow.user_id == str(user_id),
            )
        )
        return self._to_material_run(row) if row is not None else None

    def submit_direct(
        self,
        *,
        task_id: UUID,
        phenomenon: str,
        research_intent: str | None,
        context: str | None,
        now: datetime,
        input_id: UUID,
    ) -> DirectPhenomenonInput:
        row = self._session.get(PhenomenonStateRow, str(task_id))
        if row is None:
            row = PhenomenonStateRow(
                task_id=str(task_id),
                input_id=str(input_id),
                input_version=1,
                candidate_id=None,
                candidate_version=None,
                candidate_status=None,
                phenomenon=phenomenon,
                research_intent=research_intent,
                context=context,
                source_ref_ids=["input:direct"],
                evidence_refs=[],
                missing_information=[],
                source_traceability="traceable",
                content_origin="system_generated",
                model_provider=None,
                model_version=None,
                model_capability=None,
                model_degraded=None,
                knowledge_release_id=None,
                trace_id=None,
                request_id=None,
                contract_version=None,
                phenomenon_query_id=None,
                content_hash=None,
                confirmed_at=None,
                accepted_at=now,
            )
            self._session.add(row)
            self._session.flush()
        return self._to_input(row)

    def input_for_task(self, task_id: UUID) -> DirectPhenomenonInput | None:
        row = self._session.get(PhenomenonStateRow, str(task_id))
        return self._to_input(row) if row is not None else None

    def save_candidate(
        self,
        *,
        task_id: UUID,
        candidate_id: UUID,
        draft: PhenomenonCandidateDraft,
        evidence_refs: tuple[PhenomenonEvidenceRefSnapshot, ...],
        model: PhenomenonModelSnapshot,
        now: datetime,
    ) -> PhenomenonCandidate:
        row = self._session.get(PhenomenonStateRow, str(task_id))
        if row is None:
            raise RuntimeError("direct phenomenon input is required")
        if row.candidate_id is None:
            candidate = PhenomenonCandidate(
                candidate_id=candidate_id,
                task_id=task_id,
                version=1,
                status=PhenomenonCandidateStatus.PROPOSED,
                phenomenon=draft.phenomenon,
                research_intent=draft.research_intent,
                context=draft.context,
                source_ref_ids=draft.source_ref_ids,
                evidence_refs=evidence_refs,
                model=model,
            )
            self._copy_candidate_to_state(row, candidate)
            self._append_candidate(candidate, now=now)
            self._session.flush()
        return self._to_candidate(row)

    def get_candidate(
        self,
        task_id: UUID,
        candidate_id: UUID,
        version: int | None = None,
    ) -> PhenomenonCandidate | None:
        if version is not None:
            row = self._session.scalar(
                select(PhenomenonCandidateVersionRow).where(
                    PhenomenonCandidateVersionRow.task_id == str(task_id),
                    PhenomenonCandidateVersionRow.candidate_id == str(candidate_id),
                    PhenomenonCandidateVersionRow.version == version,
                )
            )
            return self._to_versioned_candidate(row) if row is not None else None

        state = self._session.get(PhenomenonStateRow, str(task_id))
        if state is not None and state.candidate_id == str(candidate_id):
            return self._to_candidate(state)
        row = self._session.scalar(
            select(PhenomenonCandidateVersionRow)
            .where(
                PhenomenonCandidateVersionRow.task_id == str(task_id),
                PhenomenonCandidateVersionRow.candidate_id == str(candidate_id),
            )
            .order_by(PhenomenonCandidateVersionRow.version.desc())
            .limit(1)
        )
        return self._to_versioned_candidate(row) if row is not None else None

    def update_candidate(
        self,
        *,
        task_id: UUID,
        candidate_id: UUID,
        expected_version: int,
        phenomenon: str,
        research_intent: str | None,
        context: str | None,
        now: datetime,
    ) -> PhenomenonCandidate | None:
        current = self.get_candidate(task_id, candidate_id)
        if (
            current is None
            or current.version != expected_version
            or current.status is PhenomenonCandidateStatus.CONFIRMED
        ):
            return None
        updated = replace(
            current,
            version=current.version + 1,
            status=PhenomenonCandidateStatus.EDITED,
            content_origin="user_modified",
            phenomenon=phenomenon.strip(),
            research_intent=research_intent,
            context=context,
        )
        self._append_candidate(updated, now=now)
        state = self._session.get(PhenomenonStateRow, str(task_id))
        if state is not None and state.candidate_id == str(candidate_id):
            self._copy_candidate_to_state(state, updated)
        self._session.flush()
        return updated

    def confirm_candidate(
        self,
        *,
        task_id: UUID,
        candidate_id: UUID,
        expected_version: int,
        query_id: UUID,
        now: datetime,
    ) -> tuple[ConfirmedPhenomenonSnapshot, datetime] | None:
        current = self.get_candidate(task_id, candidate_id)
        if current is None or current.version != expected_version:
            return None
        state = self._session.get(PhenomenonStateRow, str(task_id))
        if state is None:
            return None
        if (
            state.phenomenon_query_id is not None
            and state.candidate_id != str(candidate_id)
        ):
            return None
        if current.status is not PhenomenonCandidateStatus.CONFIRMED:
            current = replace(
                current,
                version=current.version + 1,
                status=PhenomenonCandidateStatus.CONFIRMED,
            )
            self._append_candidate(current, now=now)
            self._copy_candidate_to_state(state, current)
            state.phenomenon_query_id = str(query_id)
            state.content_hash = self._content_hash(current)
            state.confirmed_at = now
            self._session.flush()
        return self._to_snapshot(state), _as_utc(state.confirmed_at)

    def progress(self, task_id: UUID) -> PhenomenonProgress:
        row = self._session.get(PhenomenonStateRow, str(task_id))
        if row is None or row.candidate_id is None:
            return PhenomenonProgress(candidate=None, confirmed=None, confirmed_at=None)
        candidate = self._to_candidate(row)
        if row.phenomenon_query_id is None or row.confirmed_at is None:
            return PhenomenonProgress(candidate=candidate, confirmed=None, confirmed_at=None)
        return PhenomenonProgress(
            candidate=candidate,
            confirmed=self._to_snapshot(row),
            confirmed_at=_as_utc(row.confirmed_at),
        )

    def _to_material_run(self, row: MaterialIntakeRunRow) -> MaterialIntakeRun:
        candidates = tuple(
            candidate
            for candidate_id in row.candidate_ids
            if (candidate := self.get_candidate(UUID(row.task_id), UUID(candidate_id)))
            is not None
        )
        return MaterialIntakeRun(
            run_id=UUID(row.run_id),
            task_id=UUID(row.task_id),
            status=row.status,
            filename=row.filename,
            media_type=row.media_type,
            processing_policy_version=row.processing_policy_version,
            candidates=candidates,
            accepted_at=_as_utc(row.accepted_at),
        )

    def _append_candidate(
        self,
        candidate: PhenomenonCandidate,
        *,
        now: datetime,
    ) -> None:
        self._session.add(
            PhenomenonCandidateVersionRow(
                candidate_id=str(candidate.candidate_id),
                version=candidate.version,
                task_id=str(candidate.task_id),
                status=candidate.status.value,
                phenomenon=candidate.phenomenon,
                research_intent=candidate.research_intent,
                context=candidate.context,
                source_ref_ids=list(candidate.source_ref_ids),
                evidence_refs=[
                    self._evidence_to_json(item) for item in candidate.evidence_refs
                ],
                missing_information=list(candidate.missing_information),
                source_traceability=candidate.source_traceability,
                content_origin=candidate.content_origin,
                model_provider=candidate.model.provider,
                model_version=candidate.model.model_version,
                model_capability=candidate.model.capability,
                model_degraded=candidate.model.degraded,
                knowledge_release_id=candidate.model.knowledge_release_id,
                trace_id=str(candidate.model.trace_id),
                request_id=str(candidate.model.request_id),
                contract_version=candidate.model.contract_version,
                created_at=now,
            )
        )

    @classmethod
    def _copy_candidate_to_state(
        cls,
        row: PhenomenonStateRow,
        candidate: PhenomenonCandidate,
    ) -> None:
        row.candidate_id = str(candidate.candidate_id)
        row.candidate_version = candidate.version
        row.candidate_status = candidate.status.value
        row.phenomenon = candidate.phenomenon
        row.research_intent = candidate.research_intent
        row.context = candidate.context
        row.source_ref_ids = list(candidate.source_ref_ids)
        row.evidence_refs = [
            cls._evidence_to_json(item) for item in candidate.evidence_refs
        ]
        row.missing_information = list(candidate.missing_information)
        row.source_traceability = candidate.source_traceability
        row.content_origin = candidate.content_origin
        row.model_provider = candidate.model.provider
        row.model_version = candidate.model.model_version
        row.model_capability = candidate.model.capability
        row.model_degraded = candidate.model.degraded
        row.knowledge_release_id = candidate.model.knowledge_release_id
        row.trace_id = str(candidate.model.trace_id)
        row.request_id = str(candidate.model.request_id)
        row.contract_version = candidate.model.contract_version
        row.content_hash = None

    @staticmethod
    def _to_input(row: PhenomenonStateRow) -> DirectPhenomenonInput:
        return DirectPhenomenonInput(
            input_id=UUID(row.input_id),
            task_id=UUID(row.task_id),
            version=row.input_version,
            phenomenon=row.phenomenon,
            research_intent=row.research_intent,
            context=row.context,
            source_ref_ids=tuple(row.source_ref_ids),
            accepted_at=_as_utc(row.accepted_at),
        )

    @classmethod
    def _to_candidate(cls, row: PhenomenonStateRow) -> PhenomenonCandidate:
        assert row.candidate_id is not None
        assert row.candidate_version is not None
        assert row.candidate_status is not None
        assert row.model_provider is not None
        assert row.model_version is not None
        assert row.model_capability is not None
        assert row.model_degraded is not None
        assert row.trace_id is not None
        assert row.request_id is not None
        assert row.contract_version is not None
        return PhenomenonCandidate(
            candidate_id=UUID(row.candidate_id),
            task_id=UUID(row.task_id),
            version=row.candidate_version,
            status=PhenomenonCandidateStatus(row.candidate_status),
            phenomenon=row.phenomenon,
            research_intent=row.research_intent,
            context=row.context,
            source_ref_ids=tuple(row.source_ref_ids),
            evidence_refs=tuple(
                cls._evidence_from_json(item) for item in row.evidence_refs
            ),
            model=PhenomenonModelSnapshot(
                provider=row.model_provider,
                model_version=row.model_version,
                capability=row.model_capability,
                degraded=row.model_degraded,
                knowledge_release_id=row.knowledge_release_id,
                trace_id=UUID(row.trace_id),
                request_id=UUID(row.request_id),
                contract_version=row.contract_version,
            ),
            missing_information=tuple(row.missing_information),
            source_traceability=row.source_traceability,
            content_origin=row.content_origin,
        )

    @classmethod
    def _to_versioned_candidate(
        cls,
        row: PhenomenonCandidateVersionRow,
    ) -> PhenomenonCandidate:
        return PhenomenonCandidate(
            candidate_id=UUID(row.candidate_id),
            task_id=UUID(row.task_id),
            version=row.version,
            status=PhenomenonCandidateStatus(row.status),
            phenomenon=row.phenomenon,
            research_intent=row.research_intent,
            context=row.context,
            source_ref_ids=tuple(row.source_ref_ids),
            evidence_refs=tuple(
                cls._evidence_from_json(item) for item in row.evidence_refs
            ),
            model=PhenomenonModelSnapshot(
                provider=row.model_provider,
                model_version=row.model_version,
                capability=row.model_capability,
                degraded=row.model_degraded,
                knowledge_release_id=row.knowledge_release_id,
                trace_id=UUID(row.trace_id),
                request_id=UUID(row.request_id),
                contract_version=row.contract_version,
            ),
            missing_information=tuple(row.missing_information),
            source_traceability=row.source_traceability,
            content_origin=row.content_origin,
        )

    @classmethod
    def _to_snapshot(cls, row: PhenomenonStateRow) -> ConfirmedPhenomenonSnapshot:
        assert row.phenomenon_query_id is not None
        assert row.candidate_version is not None
        return ConfirmedPhenomenonSnapshot(
            task_id=UUID(row.task_id),
            phenomenon_query_id=UUID(row.phenomenon_query_id),
            version=row.candidate_version,
            phenomenon=row.phenomenon,
            research_intent=row.research_intent,
            context=row.context,
            content_hash=row.content_hash or "",
            evidence_refs=tuple(
                cls._evidence_from_json(item) for item in row.evidence_refs
            ),
        )

    @classmethod
    def _content_hash(cls, candidate: PhenomenonCandidate) -> str:
        payload = {
            "phenomenon": candidate.phenomenon,
            "research_intent": candidate.research_intent,
            "context": candidate.context,
            "source_ref_ids": candidate.source_ref_ids,
            "evidence_refs": [
                cls._evidence_to_json(item) for item in candidate.evidence_refs
            ],
        }
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return sha256(encoded).hexdigest()

    @staticmethod
    def _evidence_to_json(item: PhenomenonEvidenceRefSnapshot) -> dict[str, object]:
        return {
            "evidence_ref_id": item.evidence_ref_id,
            "excerpt": item.excerpt,
            "source_ref_id": item.source_ref_id,
            "source_description": item.source_description,
            "locator": item.locator,
            "verification_status": item.verification_status.value,
            "use_boundary": item.use_boundary,
        }

    @staticmethod
    def _evidence_from_json(item: dict[str, object]) -> PhenomenonEvidenceRefSnapshot:
        return PhenomenonEvidenceRefSnapshot(
            evidence_ref_id=str(item["evidence_ref_id"]),
            excerpt=str(item["excerpt"]),
            source_ref_id=str(item["source_ref_id"]),
            source_description=(
                str(item["source_description"])
                if item.get("source_description") is not None
                else None
            ),
            locator=str(item["locator"]) if item.get("locator") is not None else None,
            verification_status=PhenomenonEvidenceVerificationStatus(
                str(item["verification_status"])
            ),
            use_boundary=str(item["use_boundary"]),
        )
