"""persist one direct phenomenon confirmation chain

Revision ID: 20260807_0059
Revises: 20260808_0003
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260807_0059"
down_revision: str | Sequence[str] | None = "20260808_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "phenomenon_states",
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("input_id", sa.String(length=36), nullable=False),
        sa.Column("input_version", sa.Integer(), nullable=False),
        sa.Column("candidate_id", sa.String(length=36), nullable=True),
        sa.Column("candidate_version", sa.Integer(), nullable=True),
        sa.Column("candidate_status", sa.String(length=32), nullable=True),
        sa.Column("phenomenon", sa.String(length=10000), nullable=False),
        sa.Column("research_intent", sa.String(length=4000), nullable=True),
        sa.Column("context", sa.String(length=10000), nullable=True),
        sa.Column("source_ref_ids", sa.JSON(), nullable=False),
        sa.Column("evidence_refs", sa.JSON(), nullable=False),
        sa.Column("model_provider", sa.String(length=128), nullable=True),
        sa.Column("model_version", sa.String(length=128), nullable=True),
        sa.Column("model_capability", sa.String(length=32), nullable=True),
        sa.Column("model_degraded", sa.Boolean(), nullable=True),
        sa.Column("knowledge_release_id", sa.String(length=128), nullable=True),
        sa.Column("trace_id", sa.String(length=36), nullable=True),
        sa.Column("request_id", sa.String(length=36), nullable=True),
        sa.Column("contract_version", sa.String(length=64), nullable=True),
        sa.Column("phenomenon_query_id", sa.String(length=36), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["task_id"], ["research_tasks.task_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("task_id"),
        sa.UniqueConstraint("candidate_id"),
        sa.UniqueConstraint("input_id"),
    )


def downgrade() -> None:
    op.drop_table("phenomenon_states")
