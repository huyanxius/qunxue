"""Enforce one active M5 handoff and document per confirmed theory plan."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260822_0007_m5"
down_revision: str | Sequence[str] | None = "20260820_0005"
branch_labels: str | Sequence[str] | None = ("m5_research_delivery",)
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "research_document_proposals",
        sa.Column("model_provider", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "research_document_proposals",
        sa.Column("model_name", sa.String(length=128), nullable=True),
    )
    op.execute(
        sa.text(
            """
            UPDATE research_document_proposals
            SET
                model_provider = (
                    SELECT agent_runs.provider
                    FROM agent_runs
                    WHERE agent_runs.run_id = research_document_proposals.agent_run_id
                ),
                model_name = (
                    SELECT agent_runs.model
                    FROM agent_runs
                    WHERE agent_runs.run_id = research_document_proposals.agent_run_id
                )
            """
        )
    )
    op.create_table(
        "research_document_identities",
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("theory_plan_id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(
            ["task_id"], ["research_tasks.task_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["theory_plan_id"],
            ["confirmed_theory_plans.theory_plan_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("task_id", "theory_plan_id"),
        sa.UniqueConstraint(
            "document_id", name="uq_research_document_identity_document"
        ),
    )
    # Preserve all historical rows. The task's current pointer wins; otherwise
    # the most recently created first version becomes the canonical M5 document.
    op.execute(
        sa.text(
            """
            INSERT INTO research_document_identities (
                task_id, theory_plan_id, document_id
            )
            SELECT
                pairs.task_id,
                pairs.theory_plan_id,
                COALESCE(
                    (
                        SELECT tasks.current_framework_id
                        FROM research_tasks AS tasks
                        WHERE tasks.task_id = pairs.task_id
                          AND EXISTS (
                              SELECT 1
                              FROM research_document_versions AS pointed
                              WHERE pointed.document_id = tasks.current_framework_id
                                AND pointed.task_id = pairs.task_id
                                AND pointed.theory_plan_id = pairs.theory_plan_id
                                AND pointed.version = 1
                          )
                    ),
                    (
                        SELECT candidate.document_id
                        FROM research_document_versions AS candidate
                        WHERE candidate.task_id = pairs.task_id
                          AND candidate.theory_plan_id = pairs.theory_plan_id
                          AND candidate.version = 1
                        ORDER BY candidate.created_at DESC, candidate.document_id DESC
                        LIMIT 1
                    )
                )
            FROM (
                SELECT DISTINCT task_id, theory_plan_id
                FROM research_document_versions
                WHERE version = 1
            ) AS pairs
            """
        )
    )
    op.create_table(
        "research_document_handoffs",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("theory_plan_id", sa.String(length=36), nullable=False),
        sa.Column("proposal_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["task_id"], ["research_tasks.task_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["theory_plan_id"],
            ["confirmed_theory_plans.theory_plan_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "task_id", "theory_plan_id"),
        sa.UniqueConstraint(
            "proposal_id", name="uq_research_document_handoff_proposal"
        ),
    )
    # Pick one canonical active handoff without rewriting historical decisions.
    # An accepted proposal for the canonical document wins, then any accepted
    # proposal, then the newest pending proposal.
    op.execute(
        sa.text(
            """
            INSERT INTO research_document_handoffs (
                user_id, task_id, theory_plan_id, proposal_id
            )
            SELECT user_id, task_id, theory_plan_id, proposal_id
            FROM (
                SELECT
                    proposals.*,
                    ROW_NUMBER() OVER (
                        PARTITION BY user_id, task_id, theory_plan_id
                        ORDER BY
                            CASE
                                WHEN status = 'accepted'
                                  AND COALESCE(result_document_id, document_id) = (
                                      SELECT identities.document_id
                                      FROM research_document_identities AS identities
                                      WHERE identities.task_id = proposals.task_id
                                        AND identities.theory_plan_id = proposals.theory_plan_id
                                  ) THEN 0
                                WHEN status = 'accepted' THEN 1
                                ELSE 2
                            END,
                            created_at DESC,
                            proposal_id DESC
                    ) AS position
                FROM research_document_proposals AS proposals
                WHERE kind = 'create' AND status IN ('pending', 'accepted')
            ) AS ranked
            WHERE position = 1
            """
        )
    )


def downgrade() -> None:
    op.drop_table("research_document_handoffs")
    op.drop_table("research_document_identities")
    op.drop_column("research_document_proposals", "model_name")
    op.drop_column("research_document_proposals", "model_provider")
