"""Allow classroom manuscripts to use document versions without a theory plan."""

import sqlalchemy as sa
from alembic import op

revision = "20260912_0450"
down_revision = "20260912_0440"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("research_document_versions") as batch:
        batch.alter_column("theory_plan_id", existing_type=sa.String(36), nullable=True)


def downgrade():
    # A populated classroom manuscript cannot be discarded by schema rollback.
    count = (
        op.get_bind()
        .execute(
            sa.text("SELECT COUNT(*) FROM research_document_versions WHERE theory_plan_id IS NULL")
        )
        .scalar()
    )
    if count:
        raise RuntimeError("Classroom documents must be retained; downgrade is unavailable.")
    with op.batch_alter_table("research_document_versions") as batch:
        batch.alter_column("theory_plan_id", existing_type=sa.String(36), nullable=False)
