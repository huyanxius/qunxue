"""Join published production password recovery and frontier migrations.

Both predecessor revisions are already deployed histories. Keep them intact so
fresh databases and either existing branch can upgrade to the same schema.
"""

revision = "20261001_0461"
down_revision = ("20260928_0460", "20261001_0460")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
