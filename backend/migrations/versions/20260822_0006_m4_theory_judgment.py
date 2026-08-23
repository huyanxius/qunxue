"""persist auditable M4 theory review records

Revision ID: 20260822_0006
Revises: 20260822_0007_m5
Create Date: 2026-08-22
"""

from collections.abc import Iterator, Sequence
from contextlib import contextmanager

import sqlalchemy as sa
from alembic import op

revision: str = "20260822_0006"
down_revision: str | Sequence[str] | None = "20260822_0007_m5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _schema_metadata(*, upgraded: bool) -> tuple[sa.Table, sa.Table, sa.Table]:
    """Describe both sides so SQLite batch DDL also works in `alembic --sql`."""

    metadata = sa.MetaData()
    sa.Table(
        "knowledge_releases",
        metadata,
        sa.Column("knowledge_release_id", sa.String(length=128), primary_key=True),
    )
    sa.Table(
        "match_runs",
        metadata,
        sa.Column("match_run_id", sa.String(length=36), primary_key=True),
    )
    sa.Table(
        "research_tasks",
        metadata,
        sa.Column("task_id", sa.String(length=36), primary_key=True),
    )

    review_columns = [
        sa.Column("knowledge_release_id", sa.String(length=128), nullable=False),
        sa.Column("review_record_id", sa.String(length=128), nullable=False),
        sa.Column("knowledge_id", sa.String(length=128), nullable=False),
        sa.Column("review_status", sa.String(length=32), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
    ]
    if upgraded:
        review_columns.extend(
            [
                sa.Column("theory_id", sa.String(length=128), nullable=True),
                sa.Column("reviewer_id", sa.String(length=128), nullable=True),
                sa.Column("reviewer_display_name", sa.String(length=256), nullable=True),
                sa.Column("reviewer_credentials", sa.Text(), nullable=True),
                sa.Column("reviewed_subject_hash", sa.String(length=72), nullable=True),
                sa.Column("decision", sa.String(length=32), nullable=True),
                sa.Column("review_notes", sa.Text(), nullable=True),
                sa.Column("attestation", sa.Text(), nullable=True),
            ]
        )
    reviews = sa.Table(
        "knowledge_entry_reviews",
        metadata,
        *review_columns,
        sa.ForeignKeyConstraint(
            ["knowledge_release_id"],
            ["knowledge_releases.knowledge_release_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("knowledge_release_id", "review_record_id"),
    )
    if upgraded:
        sa.Index(
            "ix_knowledge_entry_reviews_release_theory",
            reviews.c.knowledge_release_id,
            reviews.c.theory_id,
        )

    decision_columns = [
        sa.Column("decision_set_id", sa.String(length=36), nullable=False),
        sa.Column("match_run_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
    ]
    if upgraded:
        decision_columns.append(
            sa.Column("draft_version", sa.Integer(), nullable=False, server_default="0")
        )
    decision_columns.extend(
        [
            sa.Column("snapshot", sa.JSON(), nullable=False),
            sa.Column("idempotency_key", sa.String(length=128), nullable=True),
            sa.Column("request_hash", sa.String(length=72), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        ]
    )
    decisions = sa.Table(
        "theory_decision_sets",
        metadata,
        *decision_columns,
        sa.ForeignKeyConstraint(
            ["match_run_id"], ["match_runs.match_run_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("decision_set_id"),
        sa.UniqueConstraint(
            "match_run_id",
            *("draft_version",) if upgraded else (),
            name=(
                "uq_theory_decision_sets_match_run_draft"
                if upgraded
                else "uq_theory_decision_sets_match_run"
            ),
        ),
    )

    plans = sa.Table(
        "confirmed_theory_plans",
        metadata,
        sa.Column("theory_plan_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("match_run_id", sa.String(length=36), nullable=False),
        sa.Column("decision_set_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("adopted_candidate_ids", sa.JSON(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("request_hash", sa.String(length=72), nullable=True),
        sa.ForeignKeyConstraint(
            ["task_id"], ["research_tasks.task_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["match_run_id"], ["match_runs.match_run_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["decision_set_id"],
            ["theory_decision_sets.decision_set_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("theory_plan_id"),
        sa.UniqueConstraint("decision_set_id"),
        *(
            (sa.UniqueConstraint("task_id", name="uq_confirmed_theory_plans_task"),)
            if upgraded
            else ()
        ),
    )
    sa.Index("ix_confirmed_theory_plans_task_id", plans.c.task_id)
    return reviews, decisions, plans


_V1_REVIEWS, _V1_DECISIONS, _V1_PLANS = _schema_metadata(upgraded=False)
_V2_REVIEWS, _V2_DECISIONS, _V2_PLANS = _schema_metadata(upgraded=True)


@contextmanager
def _sqlite_batch_foreign_keys_disabled() -> Iterator[None]:
    """Prevent SQLite batch table swaps from cascading into dependent rows."""

    context = op.get_context()
    if context.dialect.name != "sqlite":
        yield
        return
    with context.autocommit_block():
        op.execute(sa.text("PRAGMA foreign_keys=OFF"))
    try:
        yield
    finally:
        with context.autocommit_block():
            op.execute(sa.text("PRAGMA foreign_keys=ON"))


def _converge_confirmed_plans_per_task() -> None:
    op.execute(
        sa.text(
            """
            WITH ranked_plans AS (
                SELECT
                    plan.theory_plan_id,
                    ROW_NUMBER() OVER (
                        PARTITION BY plan.task_id
                        ORDER BY
                            CASE
                                WHEN task.current_theory_plan_id = plan.theory_plan_id
                                    THEN 1
                                ELSE 0
                            END DESC,
                            plan.confirmed_at DESC,
                            plan.theory_plan_id DESC
                    ) AS keep_rank
                FROM confirmed_theory_plans AS plan
                JOIN research_tasks AS task ON task.task_id = plan.task_id
            )
            DELETE FROM confirmed_theory_plans
            WHERE theory_plan_id IN (
                SELECT theory_plan_id
                FROM ranked_plans
                WHERE keep_rank > 1
            )
            """
        )
    )


def _converge_decision_sets_per_match_run() -> None:
    op.execute(
        sa.text(
            """
            WITH ranked_decisions AS (
                SELECT
                    decision.decision_set_id,
                    ROW_NUMBER() OVER (
                        PARTITION BY decision.match_run_id
                        ORDER BY
                            CASE
                                WHEN EXISTS (
                                    SELECT 1
                                    FROM confirmed_theory_plans AS plan
                                    JOIN research_tasks AS task
                                        ON task.task_id = plan.task_id
                                    WHERE
                                        plan.decision_set_id = decision.decision_set_id
                                        AND task.current_theory_plan_id = plan.theory_plan_id
                                ) THEN 2
                                WHEN EXISTS (
                                    SELECT 1
                                    FROM confirmed_theory_plans AS plan
                                    WHERE plan.decision_set_id = decision.decision_set_id
                                ) THEN 1
                                ELSE 0
                            END DESC,
                            decision.draft_version DESC,
                            decision.created_at DESC,
                            decision.decision_set_id DESC
                    ) AS keep_rank
                FROM theory_decision_sets AS decision
            )
            DELETE FROM theory_decision_sets
            WHERE decision_set_id IN (
                SELECT decision_set_id
                FROM ranked_decisions
                WHERE keep_rank > 1
            )
            """
        )
    )


def upgrade() -> None:
    _converge_confirmed_plans_per_task()
    with _sqlite_batch_foreign_keys_disabled():
        _upgrade_schema()


def _upgrade_schema() -> None:
    with op.batch_alter_table(
        "knowledge_entry_reviews", copy_from=_V1_REVIEWS
    ) as batch_op:
        batch_op.add_column(sa.Column("theory_id", sa.String(length=128), nullable=True))
        batch_op.add_column(sa.Column("reviewer_id", sa.String(length=128), nullable=True))
        batch_op.add_column(
            sa.Column("reviewer_display_name", sa.String(length=256), nullable=True)
        )
        batch_op.add_column(sa.Column("reviewer_credentials", sa.Text(), nullable=True))
        batch_op.add_column(
            sa.Column("reviewed_subject_hash", sa.String(length=72), nullable=True)
        )
        batch_op.add_column(sa.Column("decision", sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column("review_notes", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("attestation", sa.Text(), nullable=True))
        batch_op.create_index(
            "ix_knowledge_entry_reviews_release_theory",
            ["knowledge_release_id", "theory_id"],
            unique=False,
        )

    op.create_table(
        "theory_decision_drafts",
        sa.Column("draft_id", sa.String(length=36), nullable=False),
        sa.Column("match_run_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["match_run_id"], ["match_runs.match_run_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("draft_id"),
        sa.UniqueConstraint("match_run_id"),
    )
    op.create_table(
        "theory_decision_draft_requests",
        sa.Column("request_record_id", sa.String(length=36), nullable=False),
        sa.Column("match_run_id", sa.String(length=36), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_hash", sa.String(length=72), nullable=False),
        sa.Column("resulting_version", sa.Integer(), nullable=False),
        sa.Column("response_snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["match_run_id"], ["match_runs.match_run_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("request_record_id"),
        sa.UniqueConstraint(
            "match_run_id",
            "idempotency_key",
            name="uq_theory_decision_draft_request",
        ),
    )
    with op.batch_alter_table(
        "theory_decision_sets", copy_from=_V1_DECISIONS
    ) as batch_op:
        batch_op.drop_constraint("uq_theory_decision_sets_match_run", type_="unique")
        batch_op.add_column(
            sa.Column(
                "draft_version",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )
        batch_op.create_unique_constraint(
            "uq_theory_decision_sets_match_run_draft",
            ["match_run_id", "draft_version"],
        )
    with op.batch_alter_table(
        "confirmed_theory_plans", copy_from=_V1_PLANS
    ) as batch_op:
        batch_op.create_unique_constraint(
            "uq_confirmed_theory_plans_task", ["task_id"]
        )


def downgrade() -> None:
    _converge_decision_sets_per_match_run()
    with _sqlite_batch_foreign_keys_disabled():
        _downgrade_schema()


def _downgrade_schema() -> None:
    with op.batch_alter_table(
        "confirmed_theory_plans", copy_from=_V2_PLANS
    ) as batch_op:
        batch_op.drop_constraint("uq_confirmed_theory_plans_task", type_="unique")
    with op.batch_alter_table(
        "theory_decision_sets", copy_from=_V2_DECISIONS
    ) as batch_op:
        batch_op.drop_constraint(
            "uq_theory_decision_sets_match_run_draft", type_="unique"
        )
        batch_op.drop_column("draft_version")
        batch_op.create_unique_constraint(
            "uq_theory_decision_sets_match_run", ["match_run_id"]
        )
    op.drop_table("theory_decision_draft_requests")
    op.drop_table("theory_decision_drafts")
    with op.batch_alter_table(
        "knowledge_entry_reviews", copy_from=_V2_REVIEWS
    ) as batch_op:
        batch_op.drop_index("ix_knowledge_entry_reviews_release_theory")
        batch_op.drop_column("attestation")
        batch_op.drop_column("review_notes")
        batch_op.drop_column("decision")
        batch_op.drop_column("reviewed_subject_hash")
        batch_op.drop_column("reviewer_credentials")
        batch_op.drop_column("reviewer_display_name")
        batch_op.drop_column("reviewer_id")
        batch_op.drop_column("theory_id")
