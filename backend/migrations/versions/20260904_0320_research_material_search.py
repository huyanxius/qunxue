"""Add the persistent FTS5 projection for research-material parse blocks."""

from alembic import op

revision = "20260904_0320"
down_revision = "20260904_0310"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE VIRTUAL TABLE research_material_search USING fts5(
            material_id UNINDEXED,
            parse_id UNINDEXED,
            segment_id UNINDEXED,
            title,
            text,
            tokenize='trigram'
        )
        """
    )
    op.execute(
        """
        CREATE TRIGGER research_material_search_block_insert
        AFTER INSERT ON research_material_blocks
        BEGIN
            INSERT INTO research_material_search(material_id, parse_id, segment_id, title, text)
            SELECT NEW.material_id, NEW.parse_id, NEW.segment_id, material.display_name, NEW.text
            FROM research_materials AS material
            WHERE material.material_id = NEW.material_id;
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER research_material_search_block_delete
        AFTER DELETE ON research_material_blocks
        BEGIN
            DELETE FROM research_material_search
            WHERE material_id = OLD.material_id
              AND parse_id = OLD.parse_id
              AND segment_id = OLD.segment_id;
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER research_material_search_title_update
        AFTER UPDATE OF display_name ON research_materials
        BEGIN
            UPDATE research_material_search
            SET title = NEW.display_name
            WHERE material_id = NEW.material_id;
        END
        """
    )
    op.execute(
        """
        INSERT INTO research_material_search(material_id, parse_id, segment_id, title, text)
        SELECT block.material_id, block.parse_id, block.segment_id,
               material.display_name, block.text
        FROM research_material_blocks AS block
        JOIN research_materials AS material ON material.material_id = block.material_id
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS research_material_search_title_update")
    op.execute("DROP TRIGGER IF EXISTS research_material_search_block_delete")
    op.execute("DROP TRIGGER IF EXISTS research_material_search_block_insert")
    op.execute("DROP TABLE IF EXISTS research_material_search")
