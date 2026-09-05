"""Honor completed user review for existing uploaded knowledge."""

from alembic import op

revision = "20260905_0350"
down_revision = "20260905_0340"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Correct import metadata across existing snapshots without changing their bytes,
    # IDs or citations. Generated relation candidates are separate from uploaded text.
    op.execute("""
        UPDATE knowledge_entry_revisions
        SET review_status = 'reviewed', rag_eligible = 1, match_eligible = 1
    """)
    op.execute("""
        UPDATE knowledge_sources
        SET verification_status = 'verified',
            use_boundary = '用户已审核的上传知识；保留原始文件与条目定位。'
        WHERE source_type = 'repository_markdown'
    """)
    op.execute("UPDATE knowledge_theory_profiles SET review_status = 'reviewed'")
    op.execute("UPDATE knowledge_entry_reviews SET review_status = 'reviewed', "
               "decision = 'approved_for_internal_match'")
    # Only the former automatic defaults are promoted; explicit user restrictions stay.
    op.execute("""
        UPDATE research_material_archive_profiles
        SET model_processing_scope = 'external_allowed',
            deidentification_status = CASE
                WHEN deidentification_status = 'pending' THEN 'not_required'
                ELSE deidentification_status END
        WHERE model_processing_scope = 'not_assessed'
    """)


def downgrade() -> None:
    # User-confirmed review is a fact; a code rollback must not mark it unreviewed.
    pass
