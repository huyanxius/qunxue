"""create relation candidate projection

Revision ID: 20260809_0002
Revises: 20260809_0001
Create Date: 2026-08-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260809_0002"
down_revision: str | Sequence[str] | None = "20260809_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "knowledge_relations",
        sa.Column("algorithm_weight", sa.Float(), nullable=True),
    )
    op.add_column(
        "knowledge_relations",
        sa.Column("algorithm_config_version", sa.String(length=64), nullable=True),
    )
    op.create_table(
        "knowledge_relation_candidates",
        sa.Column("knowledge_release_id", sa.String(length=128), nullable=False),
        sa.Column("candidate_id", sa.String(length=256), nullable=False),
        sa.Column("source_knowledge_id", sa.String(length=128), nullable=False),
        sa.Column("target_knowledge_id", sa.String(length=128), nullable=False),
        sa.Column("suggested_relation_type", sa.String(length=64), nullable=False),
        sa.Column("direction", sa.String(length=32), nullable=False),
        sa.Column("evidence_excerpt", sa.Text(), nullable=False),
        sa.Column("evidence_locator", sa.String(length=1024), nullable=False),
        sa.Column("evidence_source_id", sa.String(length=256), nullable=False),
        sa.Column("source_content_version", sa.Integer(), nullable=False),
        sa.Column("target_content_version", sa.Integer(), nullable=False),
        sa.Column("producer", sa.String(length=64), nullable=False),
        sa.Column("producer_config_version", sa.String(length=64), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("trigger_reason", sa.Text(), nullable=False),
        sa.Column("review_status", sa.String(length=32), nullable=False),
        sa.Column("review_record_id", sa.String(length=128), nullable=True),
        sa.ForeignKeyConstraint(
            ["knowledge_release_id"],
            ["knowledge_releases.knowledge_release_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("knowledge_release_id", "candidate_id"),
    )
    op.create_index(
        "ix_knowledge_relation_candidates_release_status",
        "knowledge_relation_candidates",
        ["knowledge_release_id", "review_status", "candidate_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_knowledge_relation_candidates_release_status",
        table_name="knowledge_relation_candidates",
    )
    op.drop_table("knowledge_relation_candidates")
    op.drop_column("knowledge_relations", "algorithm_config_version")
    op.drop_column("knowledge_relations", "algorithm_weight")
