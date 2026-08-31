"""SQLite rows for task-scoped qualitative analysis records."""

from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from qunxue_api.adapters.sqlite.base import Base

_DECISION_STATUS_CHECK = "status IN ('candidate', 'confirmed', 'rejected')"
_DECISION_LIFECYCLE_CHECK = """
(
    status = 'candidate'
    AND version = 1
    AND decided_at IS NULL
    AND decision_reason IS NULL
)
OR
(
    status IN ('confirmed', 'rejected')
    AND version >= 2
    AND decided_at IS NOT NULL
    AND decision_reason IS NOT NULL
)
"""


class ResearchAnalysisWriteRequestRow(Base):
    __tablename__ = "research_analysis_write_requests"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "task_id",
            "namespace",
            "idempotency_key",
            name="uq_research_analysis_write_requests_identity",
        ),
        CheckConstraint(
            "length(request_hash) = 64",
            name="ck_research_analysis_write_requests_hash",
        ),
    )

    request_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[str] = mapped_column(
        ForeignKey("research_tasks.task_id", ondelete="CASCADE"), nullable=False
    )
    namespace: Mapped[str] = mapped_column(String(32), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(512), nullable=False)
    operation: Mapped[str] = mapped_column(String(64), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    result_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    result_id: Mapped[str] = mapped_column(String(36), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ResearchAnnotationRow(Base):
    __tablename__ = "research_analysis_annotations"
    __table_args__ = (
        CheckConstraint(
            "annotation_kind IN ('descriptive', 'researcher_reflection')",
            name="ck_research_analysis_annotations_kind",
        ),
        CheckConstraint(
            "length(segment_content_hash) = 64",
            name="ck_research_analysis_annotations_segment_hash",
        ),
        CheckConstraint(
            "length(quote_hash) = 64",
            name="ck_research_analysis_annotations_quote_hash",
        ),
        CheckConstraint(
            "quote_start >= 0 AND quote_end > quote_start",
            name="ck_research_analysis_annotations_quote_range",
        ),
        CheckConstraint(
            "quote_end - quote_start = length(quote)",
            name="ck_research_analysis_annotations_quote_length",
        ),
        CheckConstraint(
            "annotation_kind != 'researcher_reflection' OR "
            "(reflection IS NOT NULL AND length(trim(reflection)) > 0)",
            name="ck_research_analysis_annotations_reflection_required",
        ),
        Index(
            "ix_research_analysis_annotations_owner_created",
            "user_id",
            "task_id",
            "created_at",
        ),
        Index(
            "ix_research_analysis_annotations_source",
            "material_id",
            "parse_id",
            "segment_id",
        ),
    )

    annotation_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[str] = mapped_column(
        ForeignKey("research_tasks.task_id", ondelete="CASCADE"), nullable=False
    )
    material_id: Mapped[str] = mapped_column(
        ForeignKey("research_materials.material_id", ondelete="RESTRICT"), nullable=False
    )
    parse_id: Mapped[str] = mapped_column(String(36), nullable=False)
    segment_id: Mapped[str] = mapped_column(String(128), nullable=False)
    segment_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    quote: Mapped[str] = mapped_column(Text, nullable=False)
    quote_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    quote_start: Mapped[int] = mapped_column(Integer, nullable=False)
    quote_end: Mapped[int] = mapped_column(Integer, nullable=False)
    locator: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    annotation_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    case_label: Mapped[str | None] = mapped_column(String(256), nullable=True)
    observed_at: Mapped[str | None] = mapped_column(String(128), nullable=True)
    note: Mapped[str] = mapped_column(Text, nullable=False)
    reflection: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ResearchCodeRow(Base):
    __tablename__ = "research_analysis_codes"
    __table_args__ = (
        CheckConstraint(
            _DECISION_STATUS_CHECK,
            name="ck_research_analysis_codes_status",
        ),
        CheckConstraint(
            _DECISION_LIFECYCLE_CHECK,
            name="ck_research_analysis_codes_lifecycle",
        ),
        Index(
            "ix_research_analysis_codes_owner_created",
            "user_id",
            "task_id",
            "created_at",
        ),
    )

    code_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[str] = mapped_column(
        ForeignKey("research_tasks.task_id", ondelete="CASCADE"), nullable=False
    )
    label: Mapped[str] = mapped_column(String(256), nullable=False)
    definition: Mapped[str] = mapped_column(Text, nullable=False)
    annotation_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    conversation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    agent_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    agent_turn_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    tool_call_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class ResearchMemoRow(Base):
    __tablename__ = "research_analysis_memos"
    __table_args__ = (
        CheckConstraint(
            "memo_kind IN ('descriptive', 'reflexive', 'analytic', 'methodological')",
            name="ck_research_analysis_memos_kind",
        ),
        CheckConstraint(
            _DECISION_STATUS_CHECK,
            name="ck_research_analysis_memos_status",
        ),
        CheckConstraint(
            _DECISION_LIFECYCLE_CHECK,
            name="ck_research_analysis_memos_lifecycle",
        ),
        Index(
            "ix_research_analysis_memos_owner_created",
            "user_id",
            "task_id",
            "created_at",
        ),
    )

    memo_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[str] = mapped_column(
        ForeignKey("research_tasks.task_id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    memo_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    annotation_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    code_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    conversation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    agent_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    agent_turn_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    tool_call_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class ResearchComparisonRow(Base):
    __tablename__ = "research_analysis_comparisons"
    __table_args__ = (
        CheckConstraint(
            _DECISION_STATUS_CHECK,
            name="ck_research_analysis_comparisons_status",
        ),
        CheckConstraint(
            _DECISION_LIFECYCLE_CHECK,
            name="ck_research_analysis_comparisons_lifecycle",
        ),
        Index(
            "ix_research_analysis_comparisons_owner_created",
            "user_id",
            "task_id",
            "created_at",
        ),
    )

    comparison_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[str] = mapped_column(
        ForeignKey("research_tasks.task_id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    case_labels: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    time_labels: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    findings: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False)
    competing_explanations: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    evidence_gaps: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    next_steps: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False)
    theory_implication: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    conversation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    agent_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    agent_turn_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    tool_call_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class ResearchCodebookEntryRow(Base):
    __tablename__ = "research_analysis_codebook_entries"
    __table_args__ = (
        CheckConstraint(
            "lifecycle IN ('active', 'merged', 'split', 'retired')",
            name="ck_research_analysis_codebook_lifecycle",
        ),
        Index(
            "ix_research_analysis_codebook_owner",
            "user_id",
            "task_id",
            "updated_at",
        ),
    )

    code_id: Mapped[str] = mapped_column(
        ForeignKey("research_analysis_codes.code_id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[str] = mapped_column(
        ForeignKey("research_tasks.task_id", ondelete="CASCADE"), nullable=False
    )
    inclusion_rules: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    exclusion_rules: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    parent_code_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    positive_example_annotation_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    negative_example_annotation_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    lifecycle: Mapped[str] = mapped_column(String(32), nullable=False)
    related_code_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revision_reason: Mapped[str] = mapped_column(Text, nullable=False)


class ResearchThemeRow(Base):
    __tablename__ = "research_analysis_themes"
    __table_args__ = (
        CheckConstraint(_DECISION_STATUS_CHECK, name="ck_research_analysis_themes_status"),
        CheckConstraint(_DECISION_LIFECYCLE_CHECK, name="ck_research_analysis_themes_lifecycle"),
        Index("ix_research_analysis_themes_owner", "user_id", "task_id", "created_at"),
    )

    theme_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[str] = mapped_column(
        ForeignKey("research_tasks.task_id", ondelete="CASCADE"), nullable=False
    )
    label: Mapped[str] = mapped_column(String(512), nullable=False)
    central_concept: Mapped[str] = mapped_column(Text, nullable=False)
    code_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    annotation_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class ResearchMemoLinkRow(Base):
    __tablename__ = "research_analysis_memo_links"
    __table_args__ = (
        CheckConstraint(
            "target_kind IN "
            "('project', 'material', 'source', 'code', 'case', 'comparison', 'draft')",
            name="ck_research_analysis_memo_links_target_kind",
        ),
        Index("ix_research_analysis_memo_links_owner", "user_id", "task_id", "created_at"),
    )

    link_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[str] = mapped_column(
        ForeignKey("research_tasks.task_id", ondelete="CASCADE"), nullable=False
    )
    memo_id: Mapped[str] = mapped_column(
        ForeignKey("research_analysis_memos.memo_id", ondelete="CASCADE"), nullable=False
    )
    target_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    target_ref: Mapped[str] = mapped_column(String(512), nullable=False)
    annotation_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ResearchCaseProfileRow(Base):
    __tablename__ = "research_analysis_case_profiles"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "task_id",
            "case_ref",
            name="uq_research_analysis_case_profiles_ref",
        ),
        Index("ix_research_analysis_case_profiles_owner", "user_id", "task_id", "updated_at"),
    )

    profile_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[str] = mapped_column(
        ForeignKey("research_tasks.task_id", ondelete="CASCADE"), nullable=False
    )
    case_ref: Mapped[str] = mapped_column(String(512), nullable=False)
    display_label: Mapped[str] = mapped_column(String(512), nullable=False)
    attributes: Mapped[list[list[str]]] = mapped_column(JSON, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    annotation_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    memo_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ResearchMatrixCellRow(Base):
    __tablename__ = "research_analysis_matrix_cells"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "task_id",
            "case_profile_id",
            "subject_kind",
            "subject_id",
            name="uq_research_analysis_matrix_cells_position",
        ),
        CheckConstraint(
            "subject_kind IN ('code', 'theme')",
            name="ck_research_analysis_matrix_cells_subject_kind",
        ),
        Index("ix_research_analysis_matrix_cells_owner", "user_id", "task_id", "updated_at"),
    )

    cell_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[str] = mapped_column(
        ForeignKey("research_tasks.task_id", ondelete="CASCADE"), nullable=False
    )
    case_profile_id: Mapped[str] = mapped_column(
        ForeignKey("research_analysis_case_profiles.profile_id", ondelete="CASCADE"),
        nullable=False,
    )
    subject_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    subject_id: Mapped[str] = mapped_column(String(36), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    annotation_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    memo_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    finding_kinds: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ResearchMethodPresetRow(Base):
    __tablename__ = "research_analysis_method_presets"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True
    )
    task_id: Mapped[str] = mapped_column(
        ForeignKey("research_tasks.task_id", ondelete="CASCADE"), primary_key=True
    )
    method: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
