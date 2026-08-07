from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import Session

from qunxue_api.adapters.sqlite import PhenomenonStateRow
from qunxue_api.modules.research_intake import (
    ConfirmedPhenomenonSnapshot,
    DirectPhenomenonInput,
    PhenomenonCandidate,
    PhenomenonCandidateDraft,
    PhenomenonCandidateStatus,
    PhenomenonEvidenceRefSnapshot,
    PhenomenonEvidenceVerificationStatus,
    PhenomenonModelSnapshot,
    PhenomenonProgress,
    PhenomenonRepository,
)


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class SqlitePhenomenonRepository(PhenomenonRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

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
                model_provider=None,
                model_version=None,
                model_capability=None,
                model_degraded=None,
                knowledge_release_id=None,
                trace_id=None,
                request_id=None,
                contract_version=None,
                phenomenon_query_id=None,
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
    ) -> PhenomenonCandidate:
        row = self._session.get(PhenomenonStateRow, str(task_id))
        if row is None:
            raise RuntimeError("direct phenomenon input is required")
        if row.candidate_id is None:
            row.candidate_id = str(candidate_id)
            row.candidate_version = 1
            row.candidate_status = PhenomenonCandidateStatus.PROPOSED.value
            row.phenomenon = draft.phenomenon
            row.research_intent = draft.research_intent
            row.context = draft.context
            row.source_ref_ids = list(draft.source_ref_ids)
            row.evidence_refs = [self._evidence_to_json(item) for item in evidence_refs]
            row.model_provider = model.provider
            row.model_version = model.model_version
            row.model_capability = model.capability
            row.model_degraded = model.degraded
            row.knowledge_release_id = model.knowledge_release_id
            row.trace_id = str(model.trace_id)
            row.request_id = str(model.request_id)
            row.contract_version = model.contract_version
            self._session.flush()
        return self._to_candidate(row)

    def get_candidate(
        self, task_id: UUID, candidate_id: UUID
    ) -> PhenomenonCandidate | None:
        row = self._session.get(PhenomenonStateRow, str(task_id))
        if row is None or row.candidate_id != str(candidate_id):
            return None
        return self._to_candidate(row)

    def update_candidate(
        self,
        *,
        task_id: UUID,
        candidate_id: UUID,
        expected_version: int,
        phenomenon: str,
        research_intent: str | None,
        context: str | None,
    ) -> PhenomenonCandidate | None:
        row = self._session.get(PhenomenonStateRow, str(task_id))
        if (
            row is None
            or row.candidate_id != str(candidate_id)
            or row.candidate_version != expected_version
            or row.candidate_status == PhenomenonCandidateStatus.CONFIRMED.value
        ):
            return None
        row.candidate_version += 1
        row.candidate_status = PhenomenonCandidateStatus.EDITED.value
        row.phenomenon = phenomenon.strip()
        row.research_intent = research_intent
        row.context = context
        self._session.flush()
        return self._to_candidate(row)

    def confirm_candidate(
        self,
        *,
        task_id: UUID,
        candidate_id: UUID,
        expected_version: int,
        query_id: UUID,
        now: datetime,
    ) -> tuple[ConfirmedPhenomenonSnapshot, datetime] | None:
        row = self._session.get(PhenomenonStateRow, str(task_id))
        if (
            row is None
            or row.candidate_id != str(candidate_id)
            or row.candidate_version != expected_version
        ):
            return None
        if row.candidate_status != PhenomenonCandidateStatus.CONFIRMED.value:
            row.candidate_version += 1
            row.candidate_status = PhenomenonCandidateStatus.CONFIRMED.value
            row.phenomenon_query_id = str(query_id)
            row.confirmed_at = now
            self._session.flush()
        return self._to_snapshot(row), _as_utc(row.confirmed_at)

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
            evidence_refs=tuple(cls._evidence_from_json(item) for item in row.evidence_refs),
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
            evidence_refs=tuple(cls._evidence_from_json(item) for item in row.evidence_refs),
        )

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
