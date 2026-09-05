"""Cache material block vectors with their immutable parse; deletion removes both."""

import sqlalchemy as sa
from alembic import op

revision = "20260905_0360"
down_revision = "20260905_0350"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "research_material_blocks",
        sa.Column("embedding_vectors", sa.JSON(), nullable=False, server_default="{}"),
    )


def downgrade():
    op.drop_column("research_material_blocks", "embedding_vectors")
