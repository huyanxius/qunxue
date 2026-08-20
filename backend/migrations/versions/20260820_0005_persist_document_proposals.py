"""persist auditable Agent document proposals"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260820_0005"
down_revision: str | Sequence[str] | None = "20260820_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "research_document_mutation_requests",
        sa.Column("request_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("operation", sa.String(length=64), nullable=False),
        sa.Column("request_hash", sa.String(length=72), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("result_id", sa.String(length=36), nullable=True),
        sa.Column("result_version", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("request_id"),
        sa.UniqueConstraint(
            "user_id",
            "idempotency_key",
            name="uq_research_document_mutation_user_key",
        ),
    )
    op.create_table(
        "research_document_proposals",
        sa.Column("proposal_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column("agent_run_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("theory_plan_id", sa.String(length=36), nullable=False),
        sa.Column("knowledge_release_id", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("proposed_sections", sa.JSON(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("request_hash", sa.String(length=72), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=True),
        sa.Column("base_document_version", sa.Integer(), nullable=True),
        sa.Column("target_section_id", sa.String(length=128), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("result_document_id", sa.String(length=36), nullable=True),
        sa.Column("result_document_version", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["agent_conversations.conversation_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["agent_run_id"], ["agent_runs.run_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["research_tasks.task_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["theory_plan_id"],
            ["confirmed_theory_plans.theory_plan_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("proposal_id"),
        sa.UniqueConstraint(
            "agent_run_id",
            "document_id",
            "base_document_version",
            "target_section_id",
            name="uq_research_document_proposal_agent_target",
        ),
    )
    op.create_index(
        "ix_research_document_proposals_user_status",
        "research_document_proposals",
        ["user_id", "status"],
    )
    op.create_index(
        "ix_research_document_proposals_document",
        "research_document_proposals",
        ["document_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_research_document_proposals_document",
        table_name="research_document_proposals",
    )
    op.drop_index(
        "ix_research_document_proposals_user_status",
        table_name="research_document_proposals",
    )
    op.drop_table("research_document_proposals")
    op.drop_table("research_document_mutation_requests")
