"""Add professional catalog, literature, case, relation and ethics metadata."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260831_0183"
down_revision: str | Sequence[str] | None = "20260831_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "research_material_batches",
        sa.Column("batch_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("batch_id"),
        sa.UniqueConstraint("user_id", "task_id", "name", name="uq_material_batch_task_name"),
    )
    op.create_index(
        "ix_material_batches_task_created",
        "research_material_batches",
        ["user_id", "task_id", "created_at"],
    )
    op.create_table(
        "research_material_collections",
        sa.Column("collection_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("parent_collection_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["parent_collection_id"],
            ["research_material_collections.collection_id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("collection_id"),
        sa.UniqueConstraint(
            "user_id", "task_id", "name", name="uq_material_collection_task_name"
        ),
    )
    op.create_index(
        "ix_material_collections_task_created",
        "research_material_collections",
        ["user_id", "task_id", "created_at"],
    )
    op.create_table(
        "research_material_archive_profiles",
        sa.Column("material_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("research_role", sa.String(length=64), nullable=False),
        sa.Column("specific_type", sa.String(length=96), nullable=False),
        sa.Column("stage", sa.String(length=32), nullable=False),
        sa.Column("batch_id", sa.String(length=36), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("collection_ids", sa.JSON(), nullable=False),
        sa.Column("sensitivity", sa.String(length=32), nullable=False),
        sa.Column("consent_scope", sa.String(length=32), nullable=False),
        sa.Column("deidentification_status", sa.String(length=32), nullable=False),
        sa.Column("model_processing_scope", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["batch_id"],
            ["research_material_batches.batch_id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["material_id"],
            ["research_materials.material_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("material_id"),
    )
    op.create_index(
        "ix_material_profiles_task_stage",
        "research_material_archive_profiles",
        ["user_id", "task_id", "stage"],
    )
    op.create_index(
        "ix_material_profiles_task_policy",
        "research_material_archive_profiles",
        ["user_id", "task_id", "model_processing_scope"],
    )
    op.create_table(
        "research_literature_entries",
        sa.Column("literature_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("item_type", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=1000), nullable=False),
        sa.Column("doi", sa.String(length=300), nullable=True),
        sa.Column("csl_data", sa.JSON(), nullable=False),
        sa.Column("attachment_material_ids", sa.JSON(), nullable=False),
        sa.Column("collection_ids", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("literature_id"),
    )
    op.create_index(
        "ix_literature_task_title",
        "research_literature_entries",
        ["user_id", "task_id", "title"],
    )
    op.create_index(
        "ix_literature_task_doi",
        "research_literature_entries",
        ["user_id", "task_id", "doi"],
    )
    op.create_table(
        "research_cases",
        sa.Column("case_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("attributes", sa.JSON(), nullable=False),
        sa.Column("material_ids", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("case_id"),
        sa.UniqueConstraint("user_id", "task_id", "name", name="uq_research_case_task_name"),
    )
    op.create_index(
        "ix_research_cases_task_created",
        "research_cases",
        ["user_id", "task_id", "created_at"],
    )
    op.create_table(
        "research_material_relations",
        sa.Column("relation_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("source_material_id", sa.String(length=36), nullable=False),
        sa.Column("target_material_id", sa.String(length=36), nullable=False),
        sa.Column("relation_type", sa.String(length=32), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_material_id"],
            ["research_materials.material_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["target_material_id"],
            ["research_materials.material_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("relation_id"),
        sa.UniqueConstraint(
            "user_id", "task_id", "source_material_id", "target_material_id", "relation_type",
            name="uq_material_relation_identity",
        ),
    )
    op.create_index(
        "ix_material_relations_task_source",
        "research_material_relations",
        ["user_id", "task_id", "source_material_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_material_relations_task_source", table_name="research_material_relations")
    op.drop_table("research_material_relations")
    op.drop_index("ix_research_cases_task_created", table_name="research_cases")
    op.drop_table("research_cases")
    op.drop_index("ix_literature_task_doi", table_name="research_literature_entries")
    op.drop_index("ix_literature_task_title", table_name="research_literature_entries")
    op.drop_table("research_literature_entries")
    op.drop_index(
        "ix_material_profiles_task_policy",
        table_name="research_material_archive_profiles",
    )
    op.drop_index(
        "ix_material_profiles_task_stage",
        table_name="research_material_archive_profiles",
    )
    op.drop_table("research_material_archive_profiles")
    op.drop_index(
        "ix_material_collections_task_created",
        table_name="research_material_collections",
    )
    op.drop_table("research_material_collections")
    op.drop_index("ix_material_batches_task_created", table_name="research_material_batches")
    op.drop_table("research_material_batches")
