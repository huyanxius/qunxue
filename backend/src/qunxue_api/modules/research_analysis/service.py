from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from qunxue_api.modules.research_analysis.domain import (
    AnalysisAnnotation,
    AnalysisCode,
    AnalysisCodeStatus,
    AnalysisMemo,
    AnalysisRecordStatus,
    AnalysisWriteRequest,
    CaseComparison,
    ComparisonFindingKind,
    ConfirmedComparisonEvidence,
    ConfirmedComparisonProjection,
    ResearchAnalysisHandoff,
)
from qunxue_api.modules.research_analysis.errors import ResearchAnalysisIdempotencyConflict
from qunxue_api.modules.research_analysis.ports import ResearchAnalysisRepository


class _MemoryRepository:
    def __init__(self) -> None:
        self.annotations: dict[UUID, AnalysisAnnotation] = {}
        self.codes: dict[UUID, AnalysisCode] = {}
        self.memos: dict[UUID, AnalysisMemo] = {}
        self.comparisons: dict[UUID, CaseComparison] = {}
        self.write_requests: dict[tuple[UUID, UUID, str, str], AnalysisWriteRequest] = {}

    def reserve_write(self, value: AnalysisWriteRequest) -> AnalysisWriteRequest:
        key = (value.user_id, value.task_id, value.namespace, value.idempotency_key)
        existing = self.write_requests.get(key)
        if existing is None:
            self.write_requests[key] = value
            return value
        if (
            existing.operation != value.operation
            or existing.request_hash != value.request_hash
            or existing.result_kind != value.result_kind
        ):
            raise ResearchAnalysisIdempotencyConflict(
                "idempotency key was already used for a different analysis write"
            )
        return existing

    def add_annotation(self, value):
        self.annotations[value.annotation_id] = value
        return value

    def add_code(self, value):
        self.codes[value.code_id] = value
        return value

    def add_memo(self, value):
        self.memos[value.memo_id] = value
        return value

    def add_comparison(self, value):
        self.comparisons[value.comparison_id] = value
        return value

    def get_code(self, code_id, *, user_id, task_id):
        return _owned(self.codes.get(code_id), user_id, task_id)

    def get_annotation(self, annotation_id, *, user_id, task_id):
        return _owned(self.annotations.get(annotation_id), user_id, task_id)

    def get_memo(self, memo_id, *, user_id, task_id):
        return _owned(self.memos.get(memo_id), user_id, task_id)

    def get_comparison(self, comparison_id, *, user_id, task_id):
        return _owned(self.comparisons.get(comparison_id), user_id, task_id)

    def list_annotations(self, *, user_id, task_id):
        return _list_owned(self.annotations.values(), user_id, task_id)

    def list_codes(self, *, user_id, task_id):
        return _list_owned(self.codes.values(), user_id, task_id)

    def list_memos(self, *, user_id, task_id):
        return _list_owned(self.memos.values(), user_id, task_id)

    def list_comparisons(self, *, user_id, task_id):
        return _list_owned(self.comparisons.values(), user_id, task_id)


def _owned(value, user_id, task_id):
    return value if value and value.user_id == user_id and value.task_id == task_id else None


def _list_owned(values, user_id, task_id):
    return tuple(item for item in values if item.user_id == user_id and item.task_id == task_id)


class ResearchAnalysisService:
    def __init__(self, repository: ResearchAnalysisRepository) -> None:
        self._repository = repository

    @classmethod
    def in_memory(cls) -> ResearchAnalysisService:
        return cls(_MemoryRepository())

    def add_annotation(self, value: AnalysisAnnotation) -> AnalysisAnnotation:
        return self._repository.add_annotation(value)

    def reserve_write(self, value: AnalysisWriteRequest) -> AnalysisWriteRequest:
        return self._repository.reserve_write(value)

    def get_annotation(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        annotation_id: UUID,
    ) -> AnalysisAnnotation | None:
        return self._repository.get_annotation(
            annotation_id,
            user_id=user_id,
            task_id=task_id,
        )

    def get_code(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        code_id: UUID,
    ) -> AnalysisCode | None:
        return self._repository.get_code(code_id, user_id=user_id, task_id=task_id)

    def get_memo(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        memo_id: UUID,
    ) -> AnalysisMemo | None:
        return self._repository.get_memo(memo_id, user_id=user_id, task_id=task_id)

    def add_code(self, value: AnalysisCode) -> AnalysisCode:
        return self._repository.add_code(value)

    def create_code(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        label: str,
        definition: str,
        annotation_ids: tuple[UUID, ...],
        source: str = "user",
        rationale: str = "用户建立的编码",
        code_id: UUID | None = None,
        now: datetime | None = None,
        conversation_id: UUID | None = None,
        agent_run_id: UUID | None = None,
        agent_turn_id: UUID | None = None,
        tool_call_id: str | None = None,
    ) -> AnalysisCode:
        annotations = {
            item.annotation_id
            for item in self._repository.list_annotations(
                user_id=user_id,
                task_id=task_id,
            )
        }
        if any(item not in annotations for item in annotation_ids):
            raise ValueError("code annotation is not owned by this research task")
        created_at = now or datetime.now(UTC)
        value = AnalysisCode.candidate(
            code_id=code_id,
            user_id=user_id,
            task_id=task_id,
            label=label,
            definition=definition,
            annotation_ids=annotation_ids,
            rationale=rationale,
            source=source,
            conversation_id=conversation_id,
            agent_run_id=agent_run_id,
            agent_turn_id=agent_turn_id,
            tool_call_id=tool_call_id,
            now=created_at,
        )
        if source == "user":
            value = value.confirm(
                user_confirmed=True,
                expected_version=value.version,
                reason="用户创建并确认",
                now=created_at,
            )
        return self._repository.add_code(value)

    def confirm_code(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        code_id: UUID,
        user_confirmed: bool,
        expected_version: int,
        reason: str,
    ) -> AnalysisCode:
        value = self._repository.get_code(code_id, user_id=user_id, task_id=task_id)
        if value is None:
            raise LookupError(code_id)
        return self._repository.add_code(
            value.confirm(
                user_confirmed=user_confirmed,
                expected_version=expected_version,
                reason=reason,
                now=datetime.now(UTC),
            )
        )

    def reject_code(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        code_id: UUID,
        user_confirmed: bool,
        expected_version: int,
        reason: str,
    ) -> AnalysisCode:
        value = self._repository.get_code(code_id, user_id=user_id, task_id=task_id)
        if value is None:
            raise LookupError(code_id)
        return self._repository.add_code(
            value.reject(
                user_confirmed=user_confirmed,
                expected_version=expected_version,
                reason=reason,
                now=datetime.now(UTC),
            )
        )

    def add_memo(self, value: AnalysisMemo) -> AnalysisMemo:
        return self._repository.add_memo(value)

    def confirm_memo(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        memo_id: UUID,
        user_confirmed: bool,
        expected_version: int,
        reason: str,
    ) -> AnalysisMemo:
        value = self._repository.get_memo(memo_id, user_id=user_id, task_id=task_id)
        if value is None:
            raise LookupError(memo_id)
        return self._repository.add_memo(
            value.confirm(
                user_confirmed=user_confirmed,
                expected_version=expected_version,
                reason=reason,
                now=datetime.now(UTC),
            )
        )

    def reject_memo(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        memo_id: UUID,
        user_confirmed: bool,
        expected_version: int,
        reason: str,
    ) -> AnalysisMemo:
        value = self._repository.get_memo(memo_id, user_id=user_id, task_id=task_id)
        if value is None:
            raise LookupError(memo_id)
        return self._repository.add_memo(
            value.reject(
                user_confirmed=user_confirmed,
                expected_version=expected_version,
                reason=reason,
                now=datetime.now(UTC),
            )
        )

    def add_comparison(self, value: CaseComparison) -> CaseComparison:
        return self._repository.add_comparison(value)

    def get_comparison(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        comparison_id: UUID,
    ) -> CaseComparison | None:
        return self._repository.get_comparison(
            comparison_id,
            user_id=user_id,
            task_id=task_id,
        )

    def confirm_comparison(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        comparison_id: UUID,
        user_confirmed: bool,
        expected_version: int,
        reason: str,
    ) -> CaseComparison:
        value = self._repository.get_comparison(comparison_id, user_id=user_id, task_id=task_id)
        if value is None:
            raise LookupError(comparison_id)
        return self._repository.add_comparison(
            value.confirm(
                user_confirmed=user_confirmed,
                expected_version=expected_version,
                reason=reason,
                now=datetime.now(UTC),
            )
        )

    def reject_comparison(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        comparison_id: UUID,
        user_confirmed: bool,
        expected_version: int,
        reason: str,
    ) -> CaseComparison:
        value = self._repository.get_comparison(
            comparison_id,
            user_id=user_id,
            task_id=task_id,
        )
        if value is None:
            raise LookupError(comparison_id)
        return self._repository.add_comparison(
            value.reject(
                user_confirmed=user_confirmed,
                expected_version=expected_version,
                reason=reason,
                now=datetime.now(UTC),
            )
        )

    def research_map_patch(
        self,
        *,
        task_id: UUID,
        user_id: UUID | None = None,
        unavailable_annotation_ids: tuple[UUID, ...] = (),
    ) -> dict[str, list[dict[str, object]]]:
        owner = user_id
        if owner is None:
            # In-memory domain tests use a task with a single owner. Production
            # callers always pass the authenticated owner.
            candidates = [
                *getattr(self._repository, "codes", {}).values(),
                *getattr(self._repository, "comparisons", {}).values(),
            ]
            owner = next(
                (item.user_id for item in candidates if item.task_id == task_id), UUID(int=0)
            )
        nodes: list[dict[str, object]] = []
        relations: list[dict[str, object]] = []
        unavailable = set(unavailable_annotation_ids)
        annotations = {
            item.annotation_id: item
            for item in self._repository.list_annotations(
                user_id=owner,
                task_id=task_id,
            )
            if item.annotation_id not in unavailable
        }
        for code in self._repository.list_codes(user_id=owner, task_id=task_id):
            if code.status is not AnalysisCodeStatus.CONFIRMED:
                continue
            nodes.append(
                {
                    "id": f"analysis-code:{code.code_id}",
                    "kind": "claim",
                    "title": code.label,
                    "summary": code.definition,
                    "status": "grounded",
                    "citation_ids": [],
                }
            )
        for comparison in self._repository.list_comparisons(user_id=owner, task_id=task_id):
            if comparison.status is not AnalysisRecordStatus.CONFIRMED:
                continue
            synthesis_id = f"analysis-comparison:{comparison.comparison_id}"
            evidence_refs = [
                _comparison_evidence_ref(
                    comparison_id=comparison.comparison_id,
                    finding_index=finding_index,
                    annotation_id=annotation_id,
                )
                for finding_index, finding in enumerate(comparison.findings)
                if finding.kind is not ComparisonFindingKind.EVIDENCE_GAP
                for annotation_id in finding.annotation_ids
                if annotation_id in annotations
            ]
            nodes.append(
                {
                    "id": synthesis_id,
                    "kind": "synthesis",
                    "title": comparison.title,
                    "summary": comparison.theory_implication,
                    "status": "grounded",
                    "citation_ids": evidence_refs,
                }
            )
            gap_statements: list[str] = []
            for finding_index, finding in enumerate(comparison.findings):
                if finding.kind is ComparisonFindingKind.EVIDENCE_GAP:
                    gap_statements.append(finding.statement)
                    continue
                finding_id = f"{synthesis_id}:finding:{finding_index}"
                finding_citations = [
                    _comparison_evidence_ref(
                        comparison_id=comparison.comparison_id,
                        finding_index=finding_index,
                        annotation_id=annotation_id,
                    )
                    for annotation_id in finding.annotation_ids
                    if annotation_id in annotations
                ]
                challenged = finding.kind in {
                    ComparisonFindingKind.COUNTEREXAMPLE,
                    ComparisonFindingKind.CONTRADICT,
                }
                nodes.append(
                    {
                        "id": finding_id,
                        "kind": "evidence",
                        "title": finding.statement,
                        "summary": _finding_label(finding.kind),
                        "status": "challenged" if challenged else "grounded",
                        "citation_ids": finding_citations,
                    }
                )
                relations.append(
                    {
                        "id": f"{finding_id}:to-synthesis",
                        "source": finding_id,
                        "target": synthesis_id,
                        "relation": (
                            "challenges"
                            if challenged
                            else "explains"
                            if finding.kind is ComparisonFindingKind.COMPETING_EXPLANATION
                            else "supports"
                        ),
                        "label": _finding_label(finding.kind),
                    }
                )
            gap_statements.extend(comparison.evidence_gaps)
            for index, gap in enumerate(dict.fromkeys(gap_statements)):
                gap_id = f"{synthesis_id}:gap:{index}"
                nodes.append(
                    {
                        "id": gap_id,
                        "kind": "gap",
                        "title": gap,
                        "summary": "已确认的比较证据缺口",
                        "status": "open",
                        "citation_ids": [],
                    }
                )
                relations.append(
                    {
                        "id": f"{synthesis_id}:refines:{index}",
                        "source": gap_id,
                        "target": synthesis_id,
                        "relation": "refines",
                        "label": "限制解释",
                    }
                )
            for index, step in enumerate(comparison.next_steps):
                step_id = f"{synthesis_id}:next:{index}"
                nodes.append(
                    {
                        "id": step_id,
                        "kind": "question",
                        "title": step.action,
                        "summary": f"下一步行动 · {_next_step_label(step.kind)}",
                        "status": "open",
                        "citation_ids": [],
                    }
                )
                relations.append(
                    {
                        "id": f"{step_id}:refines",
                        "source": step_id,
                        "target": synthesis_id,
                        "relation": "refines",
                        "label": "继续检验",
                    }
                )
        return {"nodes": nodes, "relations": relations}

    def confirmed_comparison_projection(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        unavailable_annotation_ids: tuple[UUID, ...] = (),
    ) -> ConfirmedComparisonProjection:
        """Return only user-confirmed comparisons and readable source evidence."""

        comparisons = tuple(
            item
            for item in self._repository.list_comparisons(
                user_id=user_id,
                task_id=task_id,
            )
            if item.status is AnalysisRecordStatus.CONFIRMED
        )
        unavailable = set(unavailable_annotation_ids)
        annotations = {
            item.annotation_id: item
            for item in self._repository.list_annotations(
                user_id=user_id,
                task_id=task_id,
            )
            if item.annotation_id not in unavailable
        }
        evidence_items = tuple(
            ConfirmedComparisonEvidence(
                evidence_ref_id=_comparison_evidence_ref(
                    comparison_id=comparison.comparison_id,
                    finding_index=finding_index,
                    annotation_id=annotation.annotation_id,
                ),
                comparison_id=comparison.comparison_id,
                finding_kind=finding.kind,
                statement=finding.statement,
                annotation_id=annotation.annotation_id,
                material_id=annotation.material_id,
                parse_id=annotation.parse_id,
                segment_id=annotation.segment_id,
                quote=annotation.quote,
                locator=annotation.locator,
                case_label=annotation.case_label,
                observed_at=annotation.observed_at,
            )
            for comparison in comparisons
            for finding_index, finding in enumerate(comparison.findings)
            if finding.kind is not ComparisonFindingKind.EVIDENCE_GAP
            for annotation_id in finding.annotation_ids
            if (annotation := annotations.get(annotation_id)) is not None
        )
        return ConfirmedComparisonProjection.create(
            task_id=task_id,
            comparisons=comparisons,
            evidence_items=evidence_items,
            research_map_patch=self.research_map_patch(
                user_id=user_id,
                task_id=task_id,
                unavailable_annotation_ids=unavailable_annotation_ids,
            ),
        )

    def snapshot(self, *, user_id: UUID, task_id: UUID) -> dict[str, object]:
        return {
            "schema_version": "research-analysis-v1",
            "annotations": self._repository.list_annotations(user_id=user_id, task_id=task_id),
            "codes": self._repository.list_codes(user_id=user_id, task_id=task_id),
            "memos": self._repository.list_memos(user_id=user_id, task_id=task_id),
            "comparisons": self._repository.list_comparisons(user_id=user_id, task_id=task_id),
        }

    def formal_handoff(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        unavailable_annotation_ids: tuple[UUID, ...] = (),
    ) -> ResearchAnalysisHandoff:
        codes = tuple(
            item
            for item in self._repository.list_codes(user_id=user_id, task_id=task_id)
            if item.status is AnalysisCodeStatus.CONFIRMED
        )
        memos = tuple(
            item
            for item in self._repository.list_memos(user_id=user_id, task_id=task_id)
            if item.status is AnalysisRecordStatus.CONFIRMED
        )
        comparisons = tuple(
            item
            for item in self._repository.list_comparisons(
                user_id=user_id,
                task_id=task_id,
            )
            if item.status is AnalysisRecordStatus.CONFIRMED
        )
        referenced_annotation_ids = {
            annotation_id for code in codes for annotation_id in code.annotation_ids
        }
        referenced_annotation_ids.update(
            annotation_id for memo in memos for annotation_id in memo.annotation_ids
        )
        referenced_annotation_ids.update(
            annotation_id
            for comparison in comparisons
            for finding in comparison.findings
            for annotation_id in finding.annotation_ids
        )
        unavailable = set(unavailable_annotation_ids)
        all_annotations = self._repository.list_annotations(
            user_id=user_id,
            task_id=task_id,
        )
        annotations = tuple(
            item
            for item in all_annotations
            if item.annotation_id in referenced_annotation_ids
            and item.annotation_id not in unavailable
        )
        ordered_unavailable = tuple(
            item.annotation_id
            for item in all_annotations
            if item.annotation_id in referenced_annotation_ids and item.annotation_id in unavailable
        )
        return ResearchAnalysisHandoff.create(
            task_id=task_id,
            annotations=annotations,
            codes=codes,
            memos=memos,
            comparisons=comparisons,
            unavailable_annotation_ids=ordered_unavailable,
        )


def _comparison_evidence_ref(
    *, comparison_id: UUID, finding_index: int, annotation_id: UUID
) -> str:
    return f"analysis:{comparison_id}:finding-{finding_index + 1}:{annotation_id}"


def _finding_label(kind: ComparisonFindingKind) -> str:
    return {
        ComparisonFindingKind.SUPPORT: "支持证据",
        ComparisonFindingKind.COUNTEREXAMPLE: "反例",
        ComparisonFindingKind.CONTRADICT: "矛盾材料",
        ComparisonFindingKind.COMPETING_EXPLANATION: "竞争解释",
        ComparisonFindingKind.EVIDENCE_GAP: "证据缺口",
    }[kind]


def _next_step_label(kind: str) -> str:
    return {
        "interview": "访谈",
        "observation": "观察",
        "material_collection": "材料收集",
        "research_question": "研究问题",
    }[kind]
