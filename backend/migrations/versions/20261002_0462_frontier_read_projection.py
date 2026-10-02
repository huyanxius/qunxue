"""Index lightweight frontier browse projections and revision public reads."""

import json

import sqlalchemy as sa
from alembic import op

from qunxue_api.modules.frontier_knowledge import build_read_projection

revision = "20261002_0462"
down_revision = "20261001_0461"
branch_labels = None
depends_on = None

COLUMNS = (
    ("read_browse", sa.Boolean(), False),
    ("read_available_on", sa.String(10), None),
    ("read_topic_available_on", sa.String(10), None),
    ("read_display_date", sa.String(40), ""),
    ("read_sort_date", sa.String(40), ""),
    ("read_publication_day", sa.String(10), None),
    ("read_stream", sa.String(20), "research"),
    ("read_topic_keys", sa.JSON(), []),
    ("read_lexical_text", sa.Text(), ""),
    ("read_summary", sa.JSON(), {}),
)
TABLES = (
    "frontier_records",
    "frontier_sources",
    "frontier_editorial_briefs",
    "frontier_topic_runs",
)


def upgrade():
    for name, type_, _ in COLUMNS:
        op.add_column("frontier_records", sa.Column(name, type_, nullable=True))
    connection = op.get_bind()
    table = sa.table(
        "frontier_records",
        sa.column("record_id"),
        *(sa.column(name, type_) for name, type_, _ in COLUMNS),
    )
    rows = connection.execute(sa.text("SELECT record_id, structured_json FROM frontier_records"))
    for row in rows:
        record = json.loads(row.structured_json)
        connection.execute(
            table.update()
            .where(table.c.record_id == row.record_id)
            .values(**build_read_projection(record))
        )
    op.create_index(
        "ix_frontier_browse_date_id",
        "frontier_records",
        ["is_current", "read_browse", "read_sort_date", "record_id"],
    )
    op.create_index(
        "ix_frontier_browse_available",
        "frontier_records",
        ["is_current", "read_browse", "read_available_on"],
    )
    op.create_table(
        "frontier_revision",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("revision", sa.Integer(), nullable=False),
    )
    connection.execute(sa.text("INSERT INTO frontier_revision VALUES (1, 1)"))
    for table_name in TABLES:
        for operation in ("INSERT", "UPDATE", "DELETE"):
            connection.execute(
                sa.text(f"""CREATE TRIGGER {table_name}_revision_{operation.lower()}
                AFTER {operation} ON {table_name} BEGIN
                INSERT INTO frontier_revision (id, revision) VALUES (1, 1)
                ON CONFLICT(id) DO UPDATE SET revision = revision + 1; END""")
            )


def downgrade():
    for table_name in TABLES:
        for operation in ("insert", "update", "delete"):
            op.execute(f"DROP TRIGGER IF EXISTS {table_name}_revision_{operation}")
    op.drop_table("frontier_revision")
    op.drop_index("ix_frontier_browse_date_id", table_name="frontier_records")
    op.drop_index("ix_frontier_browse_available", table_name="frontier_records")
    for name, _, _ in reversed(COLUMNS):
        op.drop_column("frontier_records", name)
