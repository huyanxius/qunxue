"""Owner- and parse-scoped cache; no user text is copied into the public index."""

from sqlalchemy import select

from qunxue_api.adapters.sqlite.research_material_model import (
    ResearchMaterialBlockRow,
    ResearchMaterialRow,
)


class SqliteMaterialVectorCache:
    def __init__(self, session, *, user_id, parse_ids):
        self._session = session
        self._user_id = user_id
        self._parse_ids = dict(parse_ids)

    def _rows(self, chunks):
        ids = {chunk.chunk_id for chunk in chunks}
        rows = {}
        for material_id, parse_id in self._parse_ids.items():
            prefix = f"material-segment:{material_id}:"
            segment_ids = [key[len(prefix) :] for key in ids if key.startswith(prefix)]
            if not segment_ids:
                continue
            values = self._session.scalars(
                select(ResearchMaterialBlockRow)
                .join(
                    ResearchMaterialRow,
                    ResearchMaterialRow.material_id == ResearchMaterialBlockRow.material_id,
                )
                .where(
                    ResearchMaterialRow.user_id == str(self._user_id),
                    ResearchMaterialRow.status != "deleted",
                    ResearchMaterialBlockRow.material_id == str(material_id),
                    ResearchMaterialBlockRow.parse_id == str(parse_id),
                    ResearchMaterialBlockRow.segment_id.in_(segment_ids),
                )
            )
            for row in values:
                key = f"material-segment:{row.material_id}:{row.segment_id}"
                if key in ids:
                    rows[key] = row
        return rows

    def get_many(self, chunks, model):
        rows = self._rows(chunks)
        return [
            rows[chunk.chunk_id].embedding_vectors.get(model)
            if chunk.chunk_id in rows and rows[chunk.chunk_id].content_hash == chunk.content_hash
            else None
            for chunk in chunks
        ]

    def put_many(self, chunks, model, vectors):
        rows = self._rows(chunks)
        for chunk, vector in zip(chunks, vectors, strict=True):
            row = rows.get(chunk.chunk_id)
            if row is not None and row.content_hash == chunk.content_hash:
                row.embedding_vectors = {**row.embedding_vectors, model: list(vector)}
        self._session.flush()
