"""Keep completed knowledge batches across retries and worker restarts."""

import sqlalchemy as sa
from alembic import op

revision = "20260908_0430"
down_revision = "20260908_0420"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "shared_documents",
        sa.Column("knowledge_checkpoints", sa.JSON(), nullable=False, server_default="{}"),
    )


def downgrade():
    op.drop_column("shared_documents", "knowledge_checkpoints")
