"""Persist the source-grounded qualitative analysis workspace."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260831_0186"
down_revision: str | Sequence[str] | None = "20260831_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "research_analysis_codebook_entries",
        sa.Column("code_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("inclusion_rules", sa.JSON(), nullable=False),
        sa.Column("exclusion_rules", sa.JSON(), nullable=False),
        sa.Column("parent_code_id", sa.String(length=36), nullable=True),
        sa.Column("positive_example_annotation_ids", sa.JSON(), nullable=False),
        sa.Column("negative_example_annotation_ids", sa.JSON(), nullable=False),
        sa.Column("lifecycle", sa.String(length=32), nullable=False),
        sa.Column("related_code_ids", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revision_reason", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "lifecycle IN ('active', 'merged', 'split', 'retired')",
            name="ck_research_analysis_codebook_lifecycle",
        ),
        sa.ForeignKeyConstraint(
            ["code_id"], ["research_analysis_codes.code_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["task_id"], ["research_tasks.task_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("code_id"),
    )
    op.create_index(
        "ix_research_analysis_codebook_owner",
        "research_analysis_codebook_entries",
        ["user_id", "task_id", "updated_at"],
    )
    op.create_table(
        "research_analysis_themes",
        sa.Column("theme_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("label", sa.String(length=512), nullable=False),
        sa.Column("central_concept", sa.Text(), nullable=False),
        sa.Column("code_ids", sa.JSON(), nullable=False),
        sa.Column("annotation_ids", sa.JSON(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('candidate', 'confirmed', 'rejected')",
            name="ck_research_analysis_themes_status",
        ),
        sa.CheckConstraint(
            """
            (status = 'candidate' AND version = 1 AND decided_at IS NULL
             AND decision_reason IS NULL)
            OR
            (status IN ('confirmed', 'rejected') AND version >= 2
             AND decided_at IS NOT NULL AND decision_reason IS NOT NULL)
            """,
            name="ck_research_analysis_themes_lifecycle",
        ),
        sa.ForeignKeyConstraint(["task_id"], ["research_tasks.task_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("theme_id"),
    )
    op.create_index(
        "ix_research_analysis_themes_owner",
        "research_analysis_themes",
        ["user_id", "task_id", "created_at"],
    )
    op.create_table(
        "research_analysis_memo_links",
        sa.Column("link_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("memo_id", sa.String(length=36), nullable=False),
        sa.Column("target_kind", sa.String(length=32), nullable=False),
        sa.Column("target_ref", sa.String(length=512), nullable=False),
        sa.Column("annotation_ids", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "target_kind IN ('project', 'material', 'source', 'code', 'case', "
            "'comparison', 'draft')",
            name="ck_research_analysis_memo_links_target_kind",
        ),
        sa.ForeignKeyConstraint(
            ["memo_id"], ["research_analysis_memos.memo_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["task_id"], ["research_tasks.task_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("link_id"),
    )
    op.create_index(
        "ix_research_analysis_memo_links_owner",
        "research_analysis_memo_links",
        ["user_id", "task_id", "created_at"],
    )
    op.create_table(
        "research_analysis_case_profiles",
        sa.Column("profile_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("case_ref", sa.String(length=512), nullable=False),
        sa.Column("display_label", sa.String(length=512), nullable=False),
        sa.Column("attributes", sa.JSON(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("annotation_ids", sa.JSON(), nullable=False),
        sa.Column("memo_ids", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["research_tasks.task_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("profile_id"),
        sa.UniqueConstraint(
            "user_id",
            "task_id",
            "case_ref",
            name="uq_research_analysis_case_profiles_ref",
        ),
    )
    op.create_index(
        "ix_research_analysis_case_profiles_owner",
        "research_analysis_case_profiles",
        ["user_id", "task_id", "updated_at"],
    )
    op.create_table(
        "research_analysis_matrix_cells",
        sa.Column("cell_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("case_profile_id", sa.String(length=36), nullable=False),
        sa.Column("subject_kind", sa.String(length=32), nullable=False),
        sa.Column("subject_id", sa.String(length=36), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("annotation_ids", sa.JSON(), nullable=False),
        sa.Column("memo_ids", sa.JSON(), nullable=False),
        sa.Column("finding_kinds", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "subject_kind IN ('code', 'theme')",
            name="ck_research_analysis_matrix_cells_subject_kind",
        ),
        sa.ForeignKeyConstraint(
            ["case_profile_id"],
            ["research_analysis_case_profiles.profile_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["task_id"], ["research_tasks.task_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("cell_id"),
        sa.UniqueConstraint(
            "user_id",
            "task_id",
            "case_profile_id",
            "subject_kind",
            "subject_id",
            name="uq_research_analysis_matrix_cells_position",
        ),
    )
    op.create_index(
        "ix_research_analysis_matrix_cells_owner",
        "research_analysis_matrix_cells",
        ["user_id", "task_id", "updated_at"],
    )
    op.create_table(
        "research_analysis_method_presets",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("method", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["research_tasks.task_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "task_id"),
    )


def downgrade() -> None:
    op.drop_table("research_analysis_method_presets")
    op.drop_index(
        "ix_research_analysis_matrix_cells_owner",
        table_name="research_analysis_matrix_cells",
    )
    op.drop_table("research_analysis_matrix_cells")
    op.drop_index(
        "ix_research_analysis_case_profiles_owner",
        table_name="research_analysis_case_profiles",
    )
    op.drop_table("research_analysis_case_profiles")
    op.drop_index(
        "ix_research_analysis_memo_links_owner",
        table_name="research_analysis_memo_links",
    )
    op.drop_table("research_analysis_memo_links")
    op.drop_index(
        "ix_research_analysis_themes_owner",
        table_name="research_analysis_themes",
    )
    op.drop_table("research_analysis_themes")
    op.drop_index(
        "ix_research_analysis_codebook_owner",
        table_name="research_analysis_codebook_entries",
    )
    op.drop_table("research_analysis_codebook_entries")
