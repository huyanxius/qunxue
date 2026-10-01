"""Persist frontier provenance, independent sources, jobs and lexical retrieval."""

import sqlalchemy as sa
from alembic import op

revision = "20261001_0460"
down_revision = "20260912_0450"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "frontier_sources",
        sa.Column("source_id", sa.String(80), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("adapter_type", sa.String(80), nullable=False),
        sa.Column("base_url", sa.Text, nullable=False),
        sa.Column("schedule_hours", sa.Integer, nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False),
        sa.Column("status", sa.String(80), nullable=False),
        sa.Column("cursor", sa.Text),
        sa.Column("last_success_at", sa.String(40)),
        sa.Column("last_error", sa.Text),
        sa.Column("config", sa.JSON, nullable=False),
    )
    op.create_table(
        "frontier_items",
        sa.Column("item_id", sa.String(160), primary_key=True),
        sa.Column(
            "source_id", sa.String(80), sa.ForeignKey("frontier_sources.source_id"), nullable=False
        ),
        sa.Column("external_id", sa.String(500), nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("doi", sa.String(300)),
        sa.Column("title_author_key", sa.String(64), nullable=False),
        sa.Column("body_hash", sa.String(64)),
        sa.Column("canonical_study_id", sa.String(160), nullable=False),
        sa.Column("dedupe_level", sa.String(40), nullable=False),
        sa.Column("original_item_id", sa.String(160)),
        sa.UniqueConstraint("source_id", "external_id", name="uq_frontier_source_external"),
    )
    for name in ("doi", "title_author_key", "body_hash", "canonical_study_id"):
        index_name = {
            "title_author_key": "ix_frontier_title_author",
            "canonical_study_id": "ix_frontier_items_canonical_study_id",
        }.get(name, f"ix_frontier_{name}")
        op.create_index(index_name, "frontier_items", [name])
    op.create_table(
        "frontier_snapshots",
        sa.Column("snapshot_id", sa.String(80), primary_key=True),
        sa.Column(
            "item_id", sa.String(160), sa.ForeignKey("frontier_items.item_id"), nullable=False
        ),
        sa.Column(
            "source_id", sa.String(80), sa.ForeignKey("frontier_sources.source_id"), nullable=False
        ),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("scope", sa.String(80), nullable=False),
        sa.Column("fetched_at", sa.String(40), nullable=False),
        sa.Column("payload", sa.JSON, nullable=False),
        sa.UniqueConstraint("item_id", "content_hash", name="uq_frontier_snapshot"),
    )
    op.create_table(
        "frontier_records",
        sa.Column("record_id", sa.String(200), primary_key=True),
        sa.Column(
            "item_id", sa.String(160), sa.ForeignKey("frontier_items.item_id"), nullable=False
        ),
        sa.Column(
            "snapshot_id",
            sa.String(80),
            sa.ForeignKey("frontier_snapshots.snapshot_id"),
            nullable=False,
        ),
        sa.Column(
            "source_id", sa.String(80), sa.ForeignKey("frontier_sources.source_id"), nullable=False
        ),
        sa.Column("canonical_study_id", sa.String(160), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("verification_status", sa.String(40), nullable=False),
        sa.Column("rag_eligible", sa.Boolean, nullable=False),
        sa.Column("is_current", sa.Boolean, nullable=False),
        sa.Column("structured_json", sa.JSON, nullable=False),
        sa.UniqueConstraint("item_id", "version", name="uq_frontier_record_version"),
    )
    op.create_index(
        "ix_frontier_records_canonical_study_id", "frontier_records", ["canonical_study_id"]
    )
    op.create_table(
        "frontier_claims",
        sa.Column("claim_id", sa.String(80), primary_key=True),
        sa.Column(
            "record_id", sa.String(200), sa.ForeignKey("frontier_records.record_id"), nullable=False
        ),
        sa.Column("claim_text", sa.Text, nullable=False),
        sa.Column("evidence_block_ids", sa.JSON, nullable=False),
        sa.Column("verifier_status", sa.String(80), nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
    )
    op.create_index("ix_frontier_claims_record_id", "frontier_claims", ["record_id"])
    op.create_table(
        "frontier_jobs",
        sa.Column("job_id", sa.String(80), primary_key=True),
        sa.Column("stage", sa.String(40), nullable=False),
        sa.Column("object_id", sa.String(200), nullable=False),
        sa.Column("idempotency_key", sa.String(500), unique=True, nullable=False),
        sa.Column("payload", sa.JSON, nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("attempt", sa.Integer, nullable=False),
        sa.Column("next_run_at", sa.Float, nullable=False),
        sa.Column("lease_until", sa.Float),
        sa.Column("lease_token", sa.String(80)),
        sa.Column("error", sa.Text),
    )
    op.create_index("ix_frontier_jobs_ready", "frontier_jobs", ["status", "next_run_at"])
    op.create_table(
        "frontier_index",
        sa.Column(
            "record_id",
            sa.String(200),
            sa.ForeignKey("frontier_records.record_id"),
            primary_key=True,
        ),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("schema_version", sa.String(40), nullable=False),
        sa.Column("lexical_text", sa.Text, nullable=False),
        sa.Column("embedding_status", sa.String(40), nullable=False),
    )
    op.create_table(
        "frontier_topic_runs",
        sa.Column("run_id", sa.String(80), primary_key=True),
        sa.Column("as_of", sa.String(10), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("method", sa.String(80), nullable=False),
        sa.Column("payload", sa.JSON, nullable=False),
    )

    op.create_table(
        "frontier_reviews",
        sa.Column("review_id", sa.String(80), primary_key=True),
        sa.Column(
            "snapshot_id",
            sa.String(80),
            sa.ForeignKey("frontier_snapshots.snapshot_id"),
            nullable=False,
        ),
        sa.Column(
            "job_id",
            sa.String(80),
            sa.ForeignKey("frontier_jobs.job_id"),
            unique=True,
            nullable=False,
        ),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("extracted", sa.JSON, nullable=False),
        sa.Column("verdicts", sa.JSON, nullable=False),
        sa.Column("error", sa.Text),
    )
    op.create_table(
        "frontier_editorial_briefs",
        sa.Column("brief_id", sa.String(100), primary_key=True),
        sa.Column("topic_key", sa.String(80), nullable=False),
        sa.Column("stream", sa.String(20), nullable=False),
        sa.Column("basis_content_hash", sa.String(64), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.Column("payload", sa.JSON, nullable=False),
    )

    op.create_table(
        "frontier_embedding_cache",
        sa.Column("model", sa.String(200), primary_key=True),
        sa.Column("schema_version", sa.String(40), primary_key=True),
        sa.Column("content_hash", sa.String(64), primary_key=True),
        sa.Column("vector", sa.JSON, nullable=False),
    )
    op.create_table(
        "frontier_vectors",
        sa.Column("chunk_id", sa.String(250), primary_key=True),
        sa.Column(
            "record_id", sa.String(200), sa.ForeignKey("frontier_records.record_id"), nullable=False
        ),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("model", sa.String(200), nullable=False),
        sa.Column("schema_version", sa.String(40), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("vector", sa.JSON, nullable=False),
    )
    op.create_index("ix_frontier_vectors_record_id", "frontier_vectors", ["record_id"])


def downgrade():
    for table in (
        "frontier_vectors",
        "frontier_embedding_cache",
        "frontier_editorial_briefs",
        "frontier_reviews",
        "frontier_topic_runs",
        "frontier_index",
        "frontier_jobs",
        "frontier_claims",
        "frontier_records",
        "frontier_snapshots",
        "frontier_items",
        "frontier_sources",
    ):
        op.drop_table(table)
