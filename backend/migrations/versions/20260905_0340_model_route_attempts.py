"""Persist content-free model-route attempt telemetry.

Revision ID: 20260905_0340
Revises: 20260904_0330
"""

import sqlalchemy as sa
from alembic import op

revision = "20260905_0340"
down_revision = "20260904_0330"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "model_route_attempts",
        sa.Column("attempt_id", sa.String(length=36), nullable=False),
        sa.Column("route_id", sa.String(length=36), nullable=False),
        sa.Column("trace_id", sa.String(length=36), nullable=False),
        sa.Column("request_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=True),
        sa.Column("agent_run_id", sa.String(length=36), nullable=True),
        sa.Column("capability", sa.String(length=64), nullable=False),
        sa.Column("endpoint_id", sa.String(length=128), nullable=False),
        sa.Column("provider", sa.String(length=128), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("fallback", sa.Boolean(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("selected", sa.Boolean(), nullable=False),
        sa.Column("failure_retryable", sa.Boolean(), nullable=True),
        sa.Column("failure_code", sa.String(length=64), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("attempt_id"),
    )
    op.create_index(
        "ix_model_route_attempts_route_id",
        "model_route_attempts",
        ["route_id"],
        unique=False,
    )
    op.create_index(
        "ix_model_route_attempts_trace_id",
        "model_route_attempts",
        ["trace_id"],
        unique=False,
    )
    op.create_index(
        "ix_model_route_attempts_agent_run_id",
        "model_route_attempts",
        ["agent_run_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_model_route_attempts_agent_run_id",
        table_name="model_route_attempts",
    )
    op.drop_index(
        "ix_model_route_attempts_trace_id",
        table_name="model_route_attempts",
    )
    op.drop_index(
        "ix_model_route_attempts_route_id",
        table_name="model_route_attempts",
    )
    op.drop_table("model_route_attempts")
