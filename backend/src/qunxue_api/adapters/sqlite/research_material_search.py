"""SQLite FTS5 projection for immutable research-material parse blocks."""

import json
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from qunxue_api.modules.research_materials import (
    MaterialFormat,
    MaterialKind,
    MaterialLocator,
    ResearchMaterialSearchHit,
    ResearchMaterialSearchResult,
)


def _literal_match_query(value: str) -> str:
    return f'"{value.replace(chr(34), chr(34) * 2)}"'


def _excerpt(value: str, query: str, *, width: int = 180) -> str:
    normalized = value.strip()
    index = normalized.casefold().find(query.casefold())
    if index < 0 or len(normalized) <= width:
        return normalized[:width]
    start = max(0, index - width // 3)
    end = min(len(normalized), start + width)
    return f"{'…' if start else ''}{normalized[start:end]}{'…' if end < len(normalized) else ''}"


class SqliteResearchMaterialSearchRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def search(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        query: str,
        material_ids: tuple[UUID, ...] = (),
        material_parse_ids: tuple[tuple[UUID, UUID], ...] = (),
        material_kind: MaterialKind | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> ResearchMaterialSearchResult:
        normalized = " ".join(query.split())
        if not normalized:
            return ResearchMaterialSearchResult(query="", total=0, items=())
        safe_limit = max(1, min(int(limit), 100))
        safe_offset = max(0, int(offset))
        filters = [
            "material.user_id = :user_id",
            "material.task_id = :task_id",
            "material.status != 'deleted'",
            "parse_version.status = 'ready'",
        ]
        parameters: dict[str, object] = {
            "user_id": str(user_id),
            "task_id": str(task_id),
            "limit": safe_limit,
            "offset": safe_offset,
        }
        if material_parse_ids:
            pairs: list[str] = []
            for index, (material_id, parse_id) in enumerate(material_parse_ids):
                pairs.append(
                    f"(search.material_id = :scope_material_{index} "
                    f"AND search.parse_id = :scope_parse_{index})"
                )
                parameters[f"scope_material_{index}"] = str(material_id)
                parameters[f"scope_parse_{index}"] = str(parse_id)
            filters.append(f"({' OR '.join(pairs)})")
        else:
            filters.append("material.status = 'ready'")
            filters.append("material.current_parse_id = search.parse_id")
            if material_ids:
                placeholders = []
                for index, material_id in enumerate(material_ids):
                    placeholders.append(f":material_{index}")
                    parameters[f"material_{index}"] = str(material_id)
                filters.append(f"search.material_id IN ({', '.join(placeholders)})")
        if material_kind is not None:
            filters.append("material.material_kind = :material_kind")
            parameters["material_kind"] = material_kind.value

        use_fts = len(normalized) >= 3
        if use_fts:
            filters.append("research_material_search MATCH :fts_query")
            parameters["fts_query"] = _literal_match_query(normalized)
            rank = "bm25(research_material_search)"
        else:
            filters.append("(search.text LIKE :like_query OR search.title LIKE :like_query)")
            parameters["like_query"] = f"%{normalized}%"
            rank = "0.0"
        where = " AND ".join(filters)
        base = f"""
            FROM research_material_search AS search
            JOIN research_materials AS material
              ON material.material_id = search.material_id
            JOIN research_material_blocks AS block
              ON block.material_id = search.material_id
             AND block.parse_id = search.parse_id
             AND block.segment_id = search.segment_id
            JOIN research_material_parse_versions AS parse_version
              ON parse_version.material_id = search.material_id
             AND parse_version.parse_id = search.parse_id
            WHERE {where}
        """
        total = int(
            self._session.execute(text(f"SELECT COUNT(*) {base}"), parameters).scalar_one()
        )
        rows = self._session.execute(
            text(
                f"""
                SELECT search.material_id, search.parse_id, search.segment_id,
                       search.title, material.material_kind, material.material_format,
                       search.text, block.locator, {rank} AS rank
                {base}
                ORDER BY rank ASC, search.material_id, search.segment_id
                LIMIT :limit OFFSET :offset
                """
            ),
            parameters,
        ).mappings()
        items = tuple(
            ResearchMaterialSearchHit(
                material_id=UUID(str(row["material_id"])),
                parse_id=UUID(str(row["parse_id"])),
                segment_id=str(row["segment_id"]),
                title=str(row["title"]),
                material_kind=MaterialKind(str(row["material_kind"])),
                material_format=MaterialFormat(str(row["material_format"])),
                excerpt=_excerpt(str(row["text"]), normalized),
                locator=MaterialLocator.from_dict(
                    json.loads(row["locator"])
                    if isinstance(row["locator"], str)
                    else row["locator"]
                ),
                score=-float(row["rank"]),
            )
            for row in rows
        )
        return ResearchMaterialSearchResult(query=normalized, total=total, items=items)
