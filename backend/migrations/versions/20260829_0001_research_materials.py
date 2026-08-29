"""Persist user-owned research materials, parse versions, and source blocks."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260829_0001"
down_revision: str | Sequence[str] | None = "20260823_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "research_materials",
        sa.Column("material_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("delete_idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("original_filename", sa.String(length=512), nullable=False),
        sa.Column("display_name", sa.String(length=512), nullable=False),
        sa.Column("media_type", sa.String(length=128), nullable=False),
        sa.Column("material_format", sa.String(length=32), nullable=False),
        sa.Column("material_kind", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("current_parse_id", sa.String(length=36), nullable=True),
        sa.Column("current_parse_version", sa.Integer(), nullable=True),
        sa.Column("processing_policy_version", sa.String(length=64), nullable=False),
        sa.Column("last_error_code", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["research_tasks.task_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("material_id"),
        sa.UniqueConstraint(
            "user_id",
            "task_id",
            "idempotency_key",
            name="uq_research_materials_user_task_request",
        ),
        sa.UniqueConstraint(
            "user_id",
            "task_id",
            "delete_idempotency_key",
            name="uq_research_materials_user_task_delete_request",
        ),
    )
    op.create_index(
        "ix_research_materials_user_task_updated",
        "research_materials",
        ["user_id", "task_id", "updated_at"],
    )
    op.create_index(
        "ix_research_materials_task_status",
        "research_materials",
        ["task_id", "status"],
    )

    op.create_table(
        "research_material_reparse_requests",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("material_id", sa.String(length=36), nullable=False),
        sa.Column("parse_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["task_id"], ["research_tasks.task_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["material_id"], ["research_materials.material_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("user_id", "task_id", "idempotency_key"),
        sa.UniqueConstraint(
            "user_id",
            "task_id",
            "idempotency_key",
            name="uq_research_material_reparse_request",
        ),
        sa.UniqueConstraint(
            "parse_id",
            name="uq_research_material_reparse_parse_id",
        ),
    )

    op.create_table(
        "research_material_blobs",
        sa.Column("material_id", sa.String(length=36), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.ForeignKeyConstraint(
            ["material_id"], ["research_materials.material_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("material_id"),
    )

    op.create_table(
        "research_material_parse_versions",
        sa.Column("parse_id", sa.String(length=36), nullable=False),
        sa.Column("material_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("parser_name", sa.String(length=128), nullable=False),
        sa.Column("parser_version", sa.String(length=128), nullable=False),
        sa.Column("schema_version", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("full_text", sa.Text(), nullable=False),
        sa.Column("structured_document", sa.JSON(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["material_id"], ["research_materials.material_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("parse_id"),
        sa.UniqueConstraint(
            "material_id",
            "version",
            name="uq_research_material_parse_material_version",
        ),
    )
    op.create_index(
        "ix_research_material_parse_material_created",
        "research_material_parse_versions",
        ["material_id", "created_at"],
    )

    op.create_table(
        "research_material_blocks",
        sa.Column("parse_id", sa.String(length=36), nullable=False),
        sa.Column("segment_id", sa.String(length=128), nullable=False),
        sa.Column("material_id", sa.String(length=36), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("locator", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["parse_id"],
            ["research_material_parse_versions.parse_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["material_id"], ["research_materials.material_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("parse_id", "segment_id"),
        sa.UniqueConstraint(
            "parse_id",
            "ordinal",
            name="uq_research_material_block_parse_ordinal",
        ),
    )
    op.create_index(
        "ix_research_material_blocks_material_parse",
        "research_material_blocks",
        ["material_id", "parse_id", "ordinal"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_research_material_blocks_material_parse",
        table_name="research_material_blocks",
    )
    op.drop_table("research_material_blocks")
    op.drop_index(
        "ix_research_material_parse_material_created",
        table_name="research_material_parse_versions",
    )
    op.drop_table("research_material_parse_versions")
    op.drop_table("research_material_blobs")
    op.drop_table("research_material_reparse_requests")
    op.drop_index("ix_research_materials_task_status", table_name="research_materials")
    op.drop_index(
        "ix_research_materials_user_task_updated",
        table_name="research_materials",
    )
    op.drop_table("research_materials")
