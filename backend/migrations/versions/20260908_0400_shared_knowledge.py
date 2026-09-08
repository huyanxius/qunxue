"""Add course sharing and independent document records without changing research ownership."""

import sqlalchemy as sa
from alembic import op

revision = "20260908_0400"
down_revision = "20260906_0390"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "agent_conversations",
        sa.Column("reference_knowledge_base_id", sa.String(36), nullable=True),
    )
    op.create_table(
        "shared_knowledge_bases",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_user_id", sa.String(36), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("request_key", sa.String(128), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("share_token", sa.String(128), nullable=False, unique=True),
        sa.Column("sharing_enabled", sa.Boolean(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("owner_user_id", "request_key"),
    )
    op.create_index(
        "ix_shared_knowledge_bases_owner_user_id", "shared_knowledge_bases", ["owner_user_id"]
    )
    op.create_table(
        "shared_knowledge_subscriptions",
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.user_id"), primary_key=True),
        sa.Column(
            "knowledge_base_id",
            sa.String(36),
            sa.ForeignKey("shared_knowledge_bases.id"),
            primary_key=True,
        ),
    )
    op.create_table(
        "shared_documents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_user_id", sa.String(36), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("request_key", sa.String(128), nullable=False),
        sa.Column("filename", sa.String(512), nullable=False),
        sa.Column("media_type", sa.String(128), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("parse_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("segments", sa.JSON(), nullable=False),
        sa.Column("vectors", sa.JSON(), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("owner_user_id", "request_key"),
    )
    op.create_index("ix_shared_documents_owner_user_id", "shared_documents", ["owner_user_id"])
    op.create_table(
        "shared_knowledge_documents",
        sa.Column(
            "knowledge_base_id",
            sa.String(36),
            sa.ForeignKey("shared_knowledge_bases.id"),
            primary_key=True,
        ),
        sa.Column(
            "document_id", sa.String(36), sa.ForeignKey("shared_documents.id"), primary_key=True
        ),
    )
    op.create_index(
        "ix_shared_knowledge_documents_document_id", "shared_knowledge_documents", ["document_id"]
    )


def downgrade():
    op.drop_column("agent_conversations", "reference_knowledge_base_id")
    op.drop_table("shared_knowledge_documents")
    op.drop_table("shared_documents")
    op.drop_table("shared_knowledge_subscriptions")
    op.drop_table("shared_knowledge_bases")
