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
    with op.batch_alter_table("research_tasks") as batch_op:
        batch_op.add_column(sa.Column("seed_theory_id", sa.String(128), nullable=True))
        batch_op.add_column(sa.Column("seed_theory_name", sa.String(300), nullable=True))

    examples = op.create_table(
        "phenomenon_examples",
        sa.Column("example_id", sa.String(length=64), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("phenomenon", sa.String(length=10000), nullable=False),
        sa.Column("research_intent", sa.String(length=4000), nullable=True),
        sa.Column("context", sa.String(length=10000), nullable=True),
        sa.PrimaryKeyConstraint("example_id"),
        sa.UniqueConstraint("position"),
    )
    op.bulk_insert(
        examples,
        [
            {
                "example_id": "community-mutual-aid",
                "position": 1,
                "title": "社区互助变化",
                "phenomenon": "同一社区中的互助为何逐渐减少？",
                "research_intent": "理解互助关系的变化",
                "context": "社区持续更新，成员流动增加",
            },
            {
                "example_id": "event-participation",
                "position": 2,
                "title": "活动参与衰减",
                "phenomenon": "短期活动结束后参与热情为何迅速下降？",
                "research_intent": "理解参与持续性的条件",
                "context": "活动结束后缺少后续组织安排",
            },
            {
                "example_id": "cross-org-communication",
                "position": 3,
                "title": "跨组织沟通中断",
                "phenomenon": "跨组织协作中的沟通为何反复中断？",
                "research_intent": "比较结构与互动层面的解释",
                "context": "多个组织共同推进一项长期协作",
            },
        ],
    )

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
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["task_id"], ["research_tasks.task_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("task_id"),
        sa.UniqueConstraint("candidate_id"),
        sa.UniqueConstraint("input_id"),
    )
    op.create_table(
        "phenomenon_candidate_versions",
        sa.Column("candidate_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("phenomenon", sa.String(length=10000), nullable=False),
        sa.Column("research_intent", sa.String(length=4000), nullable=True),
        sa.Column("context", sa.String(length=10000), nullable=True),
        sa.Column("source_ref_ids", sa.JSON(), nullable=False),
        sa.Column("evidence_refs", sa.JSON(), nullable=False),
        sa.Column("model_provider", sa.String(length=128), nullable=False),
        sa.Column("model_version", sa.String(length=128), nullable=False),
        sa.Column("model_capability", sa.String(length=32), nullable=False),
        sa.Column("model_degraded", sa.Boolean(), nullable=False),
        sa.Column("knowledge_release_id", sa.String(length=128), nullable=True),
        sa.Column("trace_id", sa.String(length=36), nullable=False),
        sa.Column("request_id", sa.String(length=36), nullable=False),
        sa.Column("contract_version", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["task_id"], ["research_tasks.task_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("candidate_id", "version"),
    )
    op.create_index(
        "ix_phenomenon_candidate_versions_task",
        "phenomenon_candidate_versions",
        ["task_id", "candidate_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_phenomenon_candidate_versions_task",
        table_name="phenomenon_candidate_versions",
    )
    op.drop_table("phenomenon_candidate_versions")
    op.drop_table("phenomenon_states")
    op.drop_table("phenomenon_examples")
    with op.batch_alter_table("research_tasks") as batch_op:
        batch_op.drop_column("seed_theory_name")
        batch_op.drop_column("seed_theory_id")
