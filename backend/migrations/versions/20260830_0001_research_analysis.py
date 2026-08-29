"""Persist task-scoped qualitative annotations, codes, memos, and comparisons."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260830_0001"
down_revision: str | Sequence[str] | None = "20260829_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

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


def upgrade() -> None:
    op.create_table(
        "research_analysis_write_requests",
        sa.Column("request_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("namespace", sa.String(length=32), nullable=False),
        sa.Column("idempotency_key", sa.String(length=512), nullable=False),
        sa.Column("operation", sa.String(length=64), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("result_kind", sa.String(length=32), nullable=False),
        sa.Column("result_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "length(request_hash) = 64",
            name="ck_research_analysis_write_requests_hash",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.user_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["research_tasks.task_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("request_id"),
        sa.UniqueConstraint(
            "user_id",
            "task_id",
            "namespace",
            "idempotency_key",
            name="uq_research_analysis_write_requests_identity",
        ),
    )

    op.create_table(
        "research_analysis_annotations",
        sa.Column("annotation_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("material_id", sa.String(length=36), nullable=False),
        sa.Column("parse_id", sa.String(length=36), nullable=False),
        sa.Column("segment_id", sa.String(length=128), nullable=False),
        sa.Column("segment_content_hash", sa.String(length=64), nullable=False),
        sa.Column("quote", sa.Text(), nullable=False),
        sa.Column("quote_hash", sa.String(length=64), nullable=False),
        sa.Column("quote_start", sa.Integer(), nullable=False),
        sa.Column("quote_end", sa.Integer(), nullable=False),
        sa.Column("locator", sa.JSON(), nullable=False),
        sa.Column("annotation_kind", sa.String(length=32), nullable=False),
        sa.Column("case_label", sa.String(length=256), nullable=True),
        sa.Column("observed_at", sa.String(length=128), nullable=True),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("reflection", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "annotation_kind IN ('descriptive', 'researcher_reflection')",
            name="ck_research_analysis_annotations_kind",
        ),
        sa.CheckConstraint(
            "length(segment_content_hash) = 64",
            name="ck_research_analysis_annotations_segment_hash",
        ),
        sa.CheckConstraint(
            "length(quote_hash) = 64",
            name="ck_research_analysis_annotations_quote_hash",
        ),
        sa.CheckConstraint(
            "quote_start >= 0 AND quote_end > quote_start",
            name="ck_research_analysis_annotations_quote_range",
        ),
        sa.CheckConstraint(
            "quote_end - quote_start = length(quote)",
            name="ck_research_analysis_annotations_quote_length",
        ),
        sa.CheckConstraint(
            "annotation_kind != 'researcher_reflection' OR "
            "(reflection IS NOT NULL AND length(trim(reflection)) > 0)",
            name="ck_research_analysis_annotations_reflection_required",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.user_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["research_tasks.task_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["material_id"],
            ["research_materials.material_id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("annotation_id"),
    )
    op.create_index(
        "ix_research_analysis_annotations_owner_created",
        "research_analysis_annotations",
        ["user_id", "task_id", "created_at"],
    )
    op.create_index(
        "ix_research_analysis_annotations_source",
        "research_analysis_annotations",
        ["material_id", "parse_id", "segment_id"],
    )

    op.create_table(
        "research_analysis_codes",
        sa.Column("code_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("label", sa.String(length=256), nullable=False),
        sa.Column("definition", sa.Text(), nullable=False),
        sa.Column("annotation_ids", sa.JSON(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("conversation_id", sa.String(length=36), nullable=True),
        sa.Column("agent_run_id", sa.String(length=36), nullable=True),
        sa.Column("agent_turn_id", sa.String(length=36), nullable=True),
        sa.Column("tool_call_id", sa.String(length=512), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.CheckConstraint(
            _DECISION_STATUS_CHECK,
            name="ck_research_analysis_codes_status",
        ),
        sa.CheckConstraint(
            _DECISION_LIFECYCLE_CHECK,
            name="ck_research_analysis_codes_lifecycle",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.user_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["research_tasks.task_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("code_id"),
    )
    op.create_index(
        "ix_research_analysis_codes_owner_created",
        "research_analysis_codes",
        ["user_id", "task_id", "created_at"],
    )

    op.create_table(
        "research_analysis_memos",
        sa.Column("memo_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("memo_kind", sa.String(length=32), nullable=False),
        sa.Column("annotation_ids", sa.JSON(), nullable=False),
        sa.Column("code_ids", sa.JSON(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("conversation_id", sa.String(length=36), nullable=True),
        sa.Column("agent_run_id", sa.String(length=36), nullable=True),
        sa.Column("agent_turn_id", sa.String(length=36), nullable=True),
        sa.Column("tool_call_id", sa.String(length=512), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "memo_kind IN ('descriptive', 'reflexive', 'analytic', 'methodological')",
            name="ck_research_analysis_memos_kind",
        ),
        sa.CheckConstraint(
            _DECISION_STATUS_CHECK,
            name="ck_research_analysis_memos_status",
        ),
        sa.CheckConstraint(
            _DECISION_LIFECYCLE_CHECK,
            name="ck_research_analysis_memos_lifecycle",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.user_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["research_tasks.task_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("memo_id"),
    )
    op.create_index(
        "ix_research_analysis_memos_owner_created",
        "research_analysis_memos",
        ["user_id", "task_id", "created_at"],
    )

    op.create_table(
        "research_analysis_comparisons",
        sa.Column("comparison_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("case_labels", sa.JSON(), nullable=False),
        sa.Column("time_labels", sa.JSON(), nullable=False),
        sa.Column("findings", sa.JSON(), nullable=False),
        sa.Column("competing_explanations", sa.JSON(), nullable=False),
        sa.Column("evidence_gaps", sa.JSON(), nullable=False),
        sa.Column("next_steps", sa.JSON(), nullable=False),
        sa.Column("theory_implication", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.CheckConstraint(
            _DECISION_STATUS_CHECK,
            name="ck_research_analysis_comparisons_status",
        ),
        sa.CheckConstraint(
            _DECISION_LIFECYCLE_CHECK,
            name="ck_research_analysis_comparisons_lifecycle",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.user_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["research_tasks.task_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("comparison_id"),
    )
    op.create_index(
        "ix_research_analysis_comparisons_owner_created",
        "research_analysis_comparisons",
        ["user_id", "task_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_research_analysis_comparisons_owner_created",
        table_name="research_analysis_comparisons",
    )
    op.drop_table("research_analysis_comparisons")
    op.drop_index(
        "ix_research_analysis_memos_owner_created",
        table_name="research_analysis_memos",
    )
    op.drop_table("research_analysis_memos")
    op.drop_index(
        "ix_research_analysis_codes_owner_created",
        table_name="research_analysis_codes",
    )
    op.drop_table("research_analysis_codes")
    op.drop_index(
        "ix_research_analysis_annotations_source",
        table_name="research_analysis_annotations",
    )
    op.drop_index(
        "ix_research_analysis_annotations_owner_created",
        table_name="research_analysis_annotations",
    )
    op.drop_table("research_analysis_annotations")
    op.drop_table("research_analysis_write_requests")
