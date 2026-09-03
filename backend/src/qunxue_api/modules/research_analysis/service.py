from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from qunxue_api.modules.research_analysis.domain import (
    AnalysisAnnotation,
    AnalysisAuditEvent,
    AnalysisCode,
    AnalysisCodeStatus,
    AnalysisCodingPlan,
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
from qunxue_api.modules.research_analysis.qualitative_workspace import (
    AnalysisCaseProfile,
    AnalysisMemoLink,
    AnalysisTheme,
    CaseThemeMatrix,
    CaseThemeMatrixCell,
    CodebookEntry,
    CodebookLifecycle,
    MatrixSubjectKind,
    MemoTargetKind,
    MethodPresetSelection,
    QualitativeMethod,
    QualitativeWorkspaceSnapshot,
)


class _MemoryRepository:
    def __init__(self) -> None:
        self.annotations: dict[UUID, AnalysisAnnotation] = {}
        self.codes: dict[UUID, AnalysisCode] = {}
        self.memos: dict[UUID, AnalysisMemo] = {}
        self.comparisons: dict[UUID, CaseComparison] = {}
        self.coding_plans: dict[UUID, AnalysisCodingPlan] = {}
        self.audit_events: dict[UUID, AnalysisAuditEvent] = {}
        self.write_requests: dict[tuple[UUID, UUID, str, str], AnalysisWriteRequest] = {}
        self.codebook_entries: dict[UUID, CodebookEntry] = {}
        self.themes: dict[UUID, AnalysisTheme] = {}
        self.memo_links: dict[UUID, AnalysisMemoLink] = {}
        self.case_profiles: dict[UUID, AnalysisCaseProfile] = {}
        self.matrix_cells: dict[UUID, CaseThemeMatrixCell] = {}
        self.method_selections: dict[tuple[UUID, UUID], MethodPresetSelection] = {}

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

    def get_write(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        namespace: str,
        idempotency_key: str,
    ) -> AnalysisWriteRequest | None:
        return self.write_requests.get((user_id, task_id, namespace, idempotency_key))

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

    def add_coding_plan(self, value):
        self.coding_plans[value.plan_id] = value
        return value

    def get_coding_plan(self, plan_id, *, user_id, task_id):
        return _owned(self.coding_plans.get(plan_id), user_id, task_id)

    def list_coding_plans(self, *, user_id, task_id):
        return _list_owned(self.coding_plans.values(), user_id, task_id)

    def add_audit_event(self, value):
        self.audit_events[value.event_id] = value
        return value

    def list_audit_events(self, *, user_id, task_id):
        return _list_owned(self.audit_events.values(), user_id, task_id)

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

    def add_codebook_entry(self, value):
        self.codebook_entries[value.code_id] = value
        return value

    def get_codebook_entry(self, code_id, *, user_id, task_id):
        return _owned(self.codebook_entries.get(code_id), user_id, task_id)

    def list_codebook_entries(self, *, user_id, task_id):
        return _list_owned(self.codebook_entries.values(), user_id, task_id)

    def add_theme(self, value):
        self.themes[value.theme_id] = value
        return value

    def get_theme(self, theme_id, *, user_id, task_id):
        return _owned(self.themes.get(theme_id), user_id, task_id)

    def list_themes(self, *, user_id, task_id):
        return _list_owned(self.themes.values(), user_id, task_id)

    def add_memo_link(self, value):
        self.memo_links[value.link_id] = value
        return value

    def list_memo_links(self, *, user_id, task_id):
        return _list_owned(self.memo_links.values(), user_id, task_id)

    def add_case_profile(self, value):
        self.case_profiles[value.profile_id] = value
        return value

    def get_case_profile(self, profile_id, *, user_id, task_id):
        return _owned(self.case_profiles.get(profile_id), user_id, task_id)

    def list_case_profiles(self, *, user_id, task_id):
        return _list_owned(self.case_profiles.values(), user_id, task_id)

    def add_matrix_cell(self, value):
        self.matrix_cells[value.cell_id] = value
        return value

    def list_matrix_cells(self, *, user_id, task_id):
        return _list_owned(self.matrix_cells.values(), user_id, task_id)

    def add_method_selection(self, value):
        self.method_selections[(value.user_id, value.task_id)] = value
        return value

    def get_method_selection(self, *, user_id, task_id):
        return self.method_selections.get((user_id, task_id))


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

    def list_annotations(self, *, user_id: UUID, task_id: UUID) -> tuple[AnalysisAnnotation, ...]:
        return self._repository.list_annotations(user_id=user_id, task_id=task_id)

    def list_codes(self, *, user_id: UUID, task_id: UUID) -> tuple[AnalysisCode, ...]:
        return self._repository.list_codes(user_id=user_id, task_id=task_id)

    def reserve_write(self, value: AnalysisWriteRequest) -> AnalysisWriteRequest:
        return self._repository.reserve_write(value)

    def get_write(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        namespace: str,
        idempotency_key: str,
    ) -> AnalysisWriteRequest | None:
        return self._repository.get_write(
            user_id=user_id,
            task_id=task_id,
            namespace=namespace,
            idempotency_key=idempotency_key,
        )

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

    def add_coding_plan(self, value: AnalysisCodingPlan) -> AnalysisCodingPlan:
        return self._repository.add_coding_plan(value)

    def get_coding_plan(
        self, *, user_id: UUID, task_id: UUID, plan_id: UUID
    ) -> AnalysisCodingPlan | None:
        return self._repository.get_coding_plan(plan_id, user_id=user_id, task_id=task_id)

    def list_coding_plans(self, *, user_id: UUID, task_id: UUID) -> tuple[AnalysisCodingPlan, ...]:
        return self._repository.list_coding_plans(user_id=user_id, task_id=task_id)

    def get_codebook_entry(
        self, *, user_id: UUID, task_id: UUID, code_id: UUID
    ) -> CodebookEntry | None:
        return self._repository.get_codebook_entry(code_id, user_id=user_id, task_id=task_id)

    def add_audit_event(self, value: AnalysisAuditEvent) -> AnalysisAuditEvent:
        return self._repository.add_audit_event(value)

    def list_audit_events(self, *, user_id: UUID, task_id: UUID) -> tuple[AnalysisAuditEvent, ...]:
        return self._repository.list_audit_events(user_id=user_id, task_id=task_id)

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

    def configure_codebook_entry(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        code_id: UUID,
        inclusion_rules: tuple[str, ...],
        exclusion_rules: tuple[str, ...],
        positive_example_annotation_ids: tuple[UUID, ...],
        negative_example_annotation_ids: tuple[UUID, ...],
        parent_code_id: UUID | None,
        expected_version: int | None,
        now: datetime | None = None,
    ) -> CodebookEntry:
        self._require_confirmed_codes(
            user_id=user_id,
            task_id=task_id,
            code_ids=tuple(item for item in (code_id, parent_code_id) if item is not None),
        )
        self._require_annotations(
            user_id=user_id,
            task_id=task_id,
            annotation_ids=(
                *positive_example_annotation_ids,
                *negative_example_annotation_ids,
            ),
        )
        updated_at = now or datetime.now(UTC)
        existing = self._repository.get_codebook_entry(
            code_id,
            user_id=user_id,
            task_id=task_id,
        )
        if existing is None:
            if expected_version is not None:
                raise ValueError("codebook entry does not exist")
            value = CodebookEntry.create(
                user_id=user_id,
                task_id=task_id,
                code_id=code_id,
                inclusion_rules=inclusion_rules,
                exclusion_rules=exclusion_rules,
                parent_code_id=parent_code_id,
                positive_example_annotation_ids=positive_example_annotation_ids,
                negative_example_annotation_ids=negative_example_annotation_ids,
                now=updated_at,
            )
        else:
            if expected_version is None:
                raise ValueError("expected codebook entry version is required")
            value = existing.revise(
                inclusion_rules=inclusion_rules,
                exclusion_rules=exclusion_rules,
                parent_code_id=parent_code_id,
                positive_example_annotation_ids=positive_example_annotation_ids,
                negative_example_annotation_ids=negative_example_annotation_ids,
                expected_version=expected_version,
                now=updated_at,
            )
        return self._repository.add_codebook_entry(value)

    def transition_codebook_entry(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        code_id: UUID,
        lifecycle: CodebookLifecycle,
        related_code_ids: tuple[UUID, ...],
        expected_version: int,
        reason: str,
        now: datetime | None = None,
    ) -> CodebookEntry:
        self._require_confirmed_codes(
            user_id=user_id,
            task_id=task_id,
            code_ids=(code_id, *related_code_ids),
        )
        existing = self._repository.get_codebook_entry(
            code_id,
            user_id=user_id,
            task_id=task_id,
        )
        if existing is None:
            raise LookupError(code_id)
        return self._repository.add_codebook_entry(
            existing.transition(
                lifecycle=lifecycle,
                related_code_ids=related_code_ids,
                expected_version=expected_version,
                reason=reason,
                now=now or datetime.now(UTC),
            )
        )

    def create_theme(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        label: str,
        central_concept: str,
        code_ids: tuple[UUID, ...],
        annotation_ids: tuple[UUID, ...],
        source: str,
        now: datetime | None = None,
        theme_id: UUID | None = None,
    ) -> AnalysisTheme:
        self._require_confirmed_codes(
            user_id=user_id,
            task_id=task_id,
            code_ids=code_ids,
        )
        self._require_annotations(
            user_id=user_id,
            task_id=task_id,
            annotation_ids=annotation_ids,
        )
        return self._repository.add_theme(
            AnalysisTheme.create(
                user_id=user_id,
                task_id=task_id,
                label=label,
                central_concept=central_concept,
                code_ids=code_ids,
                annotation_ids=annotation_ids,
                source=source,
                now=now or datetime.now(UTC),
                theme_id=theme_id,
            )
        )

    def confirm_theme(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        theme_id: UUID,
        expected_version: int,
        user_confirmed: bool,
        reason: str,
    ) -> AnalysisTheme:
        existing = self._repository.get_theme(
            theme_id,
            user_id=user_id,
            task_id=task_id,
        )
        if existing is None:
            raise LookupError(theme_id)
        return self._repository.add_theme(
            existing.confirm(
                user_confirmed=user_confirmed,
                expected_version=expected_version,
                reason=reason,
                now=datetime.now(UTC),
            )
        )

    def attach_memo(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        memo_id: UUID,
        target_kind: MemoTargetKind,
        target_ref: str,
        annotation_ids: tuple[UUID, ...],
        now: datetime | None = None,
    ) -> AnalysisMemoLink:
        self._require_confirmed_memos(
            user_id=user_id,
            task_id=task_id,
            memo_ids=(memo_id,),
        )
        self._require_annotations(
            user_id=user_id,
            task_id=task_id,
            annotation_ids=annotation_ids,
        )
        self._validate_memo_target(
            user_id=user_id,
            task_id=task_id,
            target_kind=target_kind,
            target_ref=target_ref,
        )
        return self._repository.add_memo_link(
            AnalysisMemoLink.create(
                user_id=user_id,
                task_id=task_id,
                memo_id=memo_id,
                target_kind=target_kind,
                target_ref=target_ref,
                annotation_ids=annotation_ids,
                now=now or datetime.now(UTC),
            )
        )

    def save_case_profile(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        case_ref: str,
        display_label: str,
        attributes: tuple[tuple[str, str], ...],
        summary: str,
        annotation_ids: tuple[UUID, ...],
        memo_ids: tuple[UUID, ...],
        expected_version: int | None,
        now: datetime | None = None,
    ) -> AnalysisCaseProfile:
        self._require_annotations(
            user_id=user_id,
            task_id=task_id,
            annotation_ids=annotation_ids,
        )
        self._require_confirmed_memos(
            user_id=user_id,
            task_id=task_id,
            memo_ids=memo_ids,
        )
        existing = next(
            (
                item
                for item in self._repository.list_case_profiles(
                    user_id=user_id,
                    task_id=task_id,
                )
                if item.case_ref == case_ref.strip()
            ),
            None,
        )
        if existing is None:
            if expected_version is not None:
                raise ValueError("case profile does not exist")
            profile_id = None
            version = 1
        else:
            if expected_version != existing.version:
                raise ValueError("stale case profile version")
            profile_id = existing.profile_id
            version = existing.version + 1
        return self._repository.add_case_profile(
            AnalysisCaseProfile.create(
                user_id=user_id,
                task_id=task_id,
                case_ref=case_ref,
                display_label=display_label,
                attributes=attributes,
                summary=summary,
                annotation_ids=annotation_ids,
                memo_ids=memo_ids,
                now=now or datetime.now(UTC),
                profile_id=profile_id,
                version=version,
            )
        )

    def save_matrix_cell(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        case_profile_id: UUID,
        subject_kind: MatrixSubjectKind,
        subject_id: UUID,
        summary: str,
        annotation_ids: tuple[UUID, ...],
        memo_ids: tuple[UUID, ...],
        finding_kinds: tuple[ComparisonFindingKind, ...],
        expected_version: int | None,
        now: datetime | None = None,
    ) -> CaseThemeMatrixCell:
        profile = self._repository.get_case_profile(
            case_profile_id,
            user_id=user_id,
            task_id=task_id,
        )
        if profile is None:
            raise LookupError(case_profile_id)
        self._require_annotations(
            user_id=user_id,
            task_id=task_id,
            annotation_ids=annotation_ids,
        )
        if not set(annotation_ids).issubset(set(profile.annotation_ids)):
            raise ValueError("matrix evidence must belong to the selected case profile")
        self._require_confirmed_memos(
            user_id=user_id,
            task_id=task_id,
            memo_ids=memo_ids,
        )
        if subject_kind is MatrixSubjectKind.CODE:
            self._require_confirmed_codes(
                user_id=user_id,
                task_id=task_id,
                code_ids=(subject_id,),
            )
        else:
            theme = self._repository.get_theme(
                subject_id,
                user_id=user_id,
                task_id=task_id,
            )
            if theme is None or theme.status is not AnalysisRecordStatus.CONFIRMED:
                raise ValueError("matrix theme must be user-confirmed")
        existing = next(
            (
                item
                for item in self._repository.list_matrix_cells(
                    user_id=user_id,
                    task_id=task_id,
                )
                if item.case_profile_id == case_profile_id
                and item.subject_kind is subject_kind
                and item.subject_id == subject_id
            ),
            None,
        )
        if existing is None:
            if expected_version is not None:
                raise ValueError("matrix cell does not exist")
            cell_id = None
            version = 1
        else:
            if expected_version != existing.version:
                raise ValueError("stale matrix cell version")
            cell_id = existing.cell_id
            version = existing.version + 1
        return self._repository.add_matrix_cell(
            CaseThemeMatrixCell.create(
                user_id=user_id,
                task_id=task_id,
                case_profile_id=case_profile_id,
                subject_kind=subject_kind,
                subject_id=subject_id,
                summary=summary,
                annotation_ids=annotation_ids,
                memo_ids=memo_ids,
                finding_kinds=finding_kinds,
                now=now or datetime.now(UTC),
                cell_id=cell_id,
                version=version,
            )
        )

    def build_case_theme_matrix(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        attribute_filters: tuple[tuple[str, str], ...] = (),
    ) -> CaseThemeMatrix:
        filters = tuple((name.strip(), value.strip()) for name, value in attribute_filters)
        profiles = tuple(
            item
            for item in self._repository.list_case_profiles(
                user_id=user_id,
                task_id=task_id,
            )
            if all(filter_item in item.attributes for filter_item in filters)
        )
        profile_ids = {item.profile_id for item in profiles}
        cells = tuple(
            item
            for item in self._repository.list_matrix_cells(
                user_id=user_id,
                task_id=task_id,
            )
            if item.case_profile_id in profile_ids
        )
        return CaseThemeMatrix(
            row_profile_ids=tuple(item.profile_id for item in profiles),
            column_subjects=tuple(
                dict.fromkeys((item.subject_kind, item.subject_id) for item in cells)
            ),
            cells=cells,
            attribute_filters=filters,
        )

    def set_method_preset(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        method: QualitativeMethod,
        expected_version: int | None,
        now: datetime | None = None,
    ) -> MethodPresetSelection:
        existing = self._repository.get_method_selection(user_id=user_id, task_id=task_id)
        if existing is None:
            if expected_version is not None:
                raise ValueError("method preset does not exist")
            version = 1
        else:
            if expected_version != existing.version:
                raise ValueError("stale method preset version")
            version = existing.version + 1
        return self._repository.add_method_selection(
            MethodPresetSelection(
                user_id=user_id,
                task_id=task_id,
                method=QualitativeMethod(method),
                version=version,
                updated_at=now or datetime.now(UTC),
            )
        )

    def qualitative_workspace_snapshot(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
    ) -> QualitativeWorkspaceSnapshot:
        method = self._repository.get_method_selection(user_id=user_id, task_id=task_id)
        if method is None:
            method = MethodPresetSelection(
                user_id=user_id,
                task_id=task_id,
                method=QualitativeMethod.THEMATIC_ANALYSIS,
                version=0,
                updated_at=datetime(1970, 1, 1, tzinfo=UTC),
            )
        themes = self._repository.list_themes(user_id=user_id, task_id=task_id)
        return QualitativeWorkspaceSnapshot.create(
            task_id=task_id,
            method_preset=method,
            codebook_entries=self._repository.list_codebook_entries(
                user_id=user_id,
                task_id=task_id,
            ),
            memo_links=self._repository.list_memo_links(user_id=user_id, task_id=task_id),
            case_profiles=self._repository.list_case_profiles(
                user_id=user_id,
                task_id=task_id,
            ),
            formal_themes=tuple(
                item for item in themes if item.status is AnalysisRecordStatus.CONFIRMED
            ),
            candidate_themes=tuple(
                item for item in themes if item.status is AnalysisRecordStatus.CANDIDATE
            ),
            matrix_cells=self._repository.list_matrix_cells(user_id=user_id, task_id=task_id),
        )

    def _require_annotations(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        annotation_ids: tuple[UUID, ...],
    ) -> None:
        owned = {
            item.annotation_id
            for item in self._repository.list_annotations(user_id=user_id, task_id=task_id)
        }
        if not annotation_ids or any(item not in owned for item in annotation_ids):
            raise ValueError("source annotation is required and must belong to this research task")

    def _require_confirmed_codes(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        code_ids: tuple[UUID, ...],
    ) -> None:
        if not code_ids:
            raise ValueError("confirmed analysis code is required")
        for code_id in code_ids:
            code = self._repository.get_code(code_id, user_id=user_id, task_id=task_id)
            if code is None or code.status is not AnalysisCodeStatus.CONFIRMED:
                raise ValueError("codebook and themes require user-confirmed codes")

    def _require_confirmed_memos(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        memo_ids: tuple[UUID, ...],
    ) -> None:
        for memo_id in memo_ids:
            memo = self._repository.get_memo(memo_id, user_id=user_id, task_id=task_id)
            if memo is None or memo.status is not AnalysisRecordStatus.CONFIRMED:
                raise ValueError("memo link requires a user-confirmed memo")

    def _validate_memo_target(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        target_kind: MemoTargetKind,
        target_ref: str,
    ) -> None:
        if target_kind is MemoTargetKind.PROJECT and target_ref != str(task_id):
            raise ValueError("project memo target must be the research task")
        if target_kind is MemoTargetKind.CODE:
            try:
                code_id = UUID(target_ref)
            except ValueError as error:
                raise ValueError("code memo target must be a code id") from error
            self._require_confirmed_codes(
                user_id=user_id,
                task_id=task_id,
                code_ids=(code_id,),
            )
        if target_kind is MemoTargetKind.COMPARISON:
            try:
                comparison_id = UUID(target_ref)
            except ValueError as error:
                raise ValueError("comparison memo target must be a comparison id") from error
            comparison = self._repository.get_comparison(
                comparison_id,
                user_id=user_id,
                task_id=task_id,
            )
            if comparison is None or comparison.status is not AnalysisRecordStatus.CONFIRMED:
                raise ValueError("memo comparison target must be user-confirmed")

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
            "coding_plans": self._repository.list_coding_plans(user_id=user_id, task_id=task_id),
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
