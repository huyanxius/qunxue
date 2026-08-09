"""create knowledge catalog release projection

Revision ID: 20260809_0001
Revises: 20260807_0059
Create Date: 2026-08-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260809_0001"
down_revision: str | Sequence[str] | None = "20260807_0059"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "knowledge_releases",
        sa.Column("knowledge_release_id", sa.String(length=128), nullable=False),
        sa.Column("level", sa.String(length=16), nullable=False),
        sa.Column("content_hash", sa.String(length=72), nullable=False),
        sa.Column("build_config_version", sa.String(length=64), nullable=False),
        sa.Column("manifest", sa.JSON(), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("built_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("knowledge_release_id"),
        sa.UniqueConstraint("content_hash"),
    )
    op.create_index(
        "ix_knowledge_releases_current",
        "knowledge_releases",
        ["is_current", "level"],
    )
    op.create_table(
        "knowledge_entry_revisions",
        sa.Column("knowledge_release_id", sa.String(length=128), nullable=False),
        sa.Column("knowledge_id", sa.String(length=128), nullable=False),
        sa.Column("content_version", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=72), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("category_id", sa.String(length=1024), nullable=True),
        sa.Column("category", sa.String(length=512), nullable=True),
        sa.Column("dimension_id", sa.String(length=16), nullable=False),
        sa.Column("dimension", sa.String(length=64), nullable=False),
        sa.Column("directory_path", sa.JSON(), nullable=False),
        sa.Column("review_status", sa.String(length=32), nullable=False),
        sa.Column("browse_eligible", sa.Boolean(), nullable=False),
        sa.Column("rag_eligible", sa.Boolean(), nullable=False),
        sa.Column("training_candidate_eligible", sa.Boolean(), nullable=False),
        sa.Column("match_eligible", sa.Boolean(), nullable=False),
        sa.Column("review_record_ids", sa.JSON(), nullable=False),
        sa.Column("aliases", sa.JSON(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source_path", sa.String(length=1024), nullable=False),
        sa.Column("source_hash", sa.String(length=72), nullable=False),
        sa.ForeignKeyConstraint(
            ["knowledge_release_id"],
            ["knowledge_releases.knowledge_release_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("knowledge_release_id", "knowledge_id"),
    )
    op.create_index(
        "ix_knowledge_entry_revisions_release_browse",
        "knowledge_entry_revisions",
        ["knowledge_release_id", "browse_eligible", "knowledge_id"],
    )
    op.create_index(
        "ix_knowledge_entry_revisions_release_dimension",
        "knowledge_entry_revisions",
        ["knowledge_release_id", "dimension_id"],
    )
    op.create_table(
        "knowledge_sources",
        sa.Column("knowledge_release_id", sa.String(length=128), nullable=False),
        sa.Column("source_id", sa.String(length=256), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=1024), nullable=False),
        sa.Column("authors_or_institution", sa.JSON(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("publication", sa.String(length=512), nullable=True),
        sa.Column("locator", sa.String(length=1024), nullable=True),
        sa.Column("url", sa.String(length=2048), nullable=True),
        sa.Column("verification_status", sa.String(length=32), nullable=False),
        sa.Column("use_boundary", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["knowledge_release_id"],
            ["knowledge_releases.knowledge_release_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("knowledge_release_id", "source_id"),
    )
    op.create_table(
        "knowledge_relations",
        sa.Column("knowledge_release_id", sa.String(length=128), nullable=False),
        sa.Column("relation_id", sa.String(length=256), nullable=False),
        sa.Column("source_knowledge_id", sa.String(length=128), nullable=False),
        sa.Column("target_knowledge_id", sa.String(length=128), nullable=False),
        sa.Column("relation_type", sa.String(length=64), nullable=False),
        sa.Column("direction", sa.String(length=32), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("evidence_source_ids", sa.JSON(), nullable=False),
        sa.Column("evidence_grade", sa.String(length=32), nullable=False),
        sa.Column("content_version", sa.Integer(), nullable=False),
        sa.Column("review_status", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(
            ["knowledge_release_id"],
            ["knowledge_releases.knowledge_release_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("knowledge_release_id", "relation_id"),
    )
    op.create_table(
        "knowledge_theory_profiles",
        sa.Column("knowledge_release_id", sa.String(length=128), nullable=False),
        sa.Column("theory_id", sa.String(length=128), nullable=False),
        sa.Column("related_knowledge_ids", sa.JSON(), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("core_propositions", sa.JSON(), nullable=False),
        sa.Column("applicable_phenomena", sa.JSON(), nullable=False),
        sa.Column("analysis_levels", sa.JSON(), nullable=False),
        sa.Column("prerequisites", sa.JSON(), nullable=False),
        sa.Column("exclusion_signals", sa.JSON(), nullable=False),
        sa.Column("observable_evidence", sa.JSON(), nullable=False),
        sa.Column("competing_or_complementary_theory_ids", sa.JSON(), nullable=False),
        sa.Column("source_ids", sa.JSON(), nullable=False),
        sa.Column("content_version", sa.Integer(), nullable=False),
        sa.Column("review_status", sa.String(length=32), nullable=False),
        sa.Column("match_eligible", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["knowledge_release_id"],
            ["knowledge_releases.knowledge_release_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("knowledge_release_id", "theory_id"),
    )
    op.create_table(
        "knowledge_entry_reviews",
        sa.Column("knowledge_release_id", sa.String(length=128), nullable=False),
        sa.Column("review_record_id", sa.String(length=128), nullable=False),
        sa.Column("knowledge_id", sa.String(length=128), nullable=False),
        sa.Column("review_status", sa.String(length=32), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["knowledge_release_id"],
            ["knowledge_releases.knowledge_release_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("knowledge_release_id", "review_record_id"),
    )
    op.execute(
        "CREATE VIRTUAL TABLE knowledge_search_fts USING fts5("
        "knowledge_release_id UNINDEXED, knowledge_id UNINDEXED, title, content, "
        "category, dimension, tokenize='trigram')"
    )


def downgrade() -> None:
    op.execute("DROP TABLE knowledge_search_fts")
    op.drop_table("knowledge_entry_reviews")
    op.drop_table("knowledge_theory_profiles")
    op.drop_table("knowledge_relations")
    op.drop_table("knowledge_sources")
    op.drop_index(
        "ix_knowledge_entry_revisions_release_dimension",
        table_name="knowledge_entry_revisions",
    )
    op.drop_index(
        "ix_knowledge_entry_revisions_release_browse",
        table_name="knowledge_entry_revisions",
    )
    op.drop_table("knowledge_entry_revisions")
    op.drop_index("ix_knowledge_releases_current", table_name="knowledge_releases")
    op.drop_table("knowledge_releases")
