"""SQLite-backed preview publication of the repository knowledge Markdown."""

import json
from base64 import urlsafe_b64decode, urlsafe_b64encode
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

from sqlalchemy import func, or_, select, text, update

from qunxue_api.adapters.knowledge_markdown import (
    ParsedKnowledgeEntry,
    parse_knowledge_markdown,
)
from qunxue_api.adapters.knowledge_relations import (
    PRODUCER_CONFIG_VERSION,
    RelationCandidateInput,
    StructuralConnectionInput,
    StructuralNodeInput,
    build_structural_connections,
    extract_relation_candidates,
)
from qunxue_api.adapters.sqlite.database import Database
from qunxue_api.adapters.sqlite.knowledge_catalog_model import (
    KnowledgeEntryRevisionRow,
    KnowledgeRelationCandidateRow,
    KnowledgeRelationRow,
    KnowledgeReleaseRow,
    KnowledgeSourceRow,
    KnowledgeTheoryProfileRow,
)
from qunxue_api.modules.knowledge_catalog import (
    KnowledgeCatalog,
    KnowledgeDirectoryFacetSnapshot,
    KnowledgeDirectoryNodeSnapshot,
    KnowledgeDirectoryNodeType,
    KnowledgeDirectorySummary,
    KnowledgeEntryDetail,
    KnowledgeEntryPage,
    KnowledgeEntrySummary,
    KnowledgeRelationPage,
    KnowledgeRelationSnapshot,
    KnowledgeReleaseLevel,
    KnowledgeReleaseManifest,
    KnowledgeReleaseRef,
    KnowledgeReviewStatus,
    KnowledgeUseEligibility,
    KnowledgeUsePurpose,
    RelationCandidatePage,
    RelationCandidateSnapshot,
    SourceRecordSnapshot,
    SourceVerificationStatus,
    StructuralConnectionPage,
    StructuralConnectionSnapshot,
    TheoryProfileSnapshot,
)

_BUILD_CONFIG_VERSION = "markdown-preview-v2+explicit-title-trigger-v1"
_DIMENSION_DIRECTORIES = (
    "本体论",
    "实践论",
    "方法论",
    "价值论",
    "认识论",
    "学派传统",
    "学科史",
)
_PREVIEW_SOURCE_BOUNDARY = "仓库 Markdown 导入溯源；不是已核验的学术来源。"


@dataclass(frozen=True, slots=True)
class _ImportedEntry:
    entry: ParsedKnowledgeEntry
    source_path: str
    source_hash: str
    content_hash: str


class SqliteKnowledgeCatalog(KnowledgeCatalog):
    def __init__(self, database: Database, *, knowledge_root: Path) -> None:
        self._database = database
        self._knowledge_root = knowledge_root

    def current_release(
        self,
        *,
        purpose: KnowledgeUsePurpose,
    ) -> KnowledgeReleaseRef:
        with self._database.session() as session:
            # Matching must stay on an explicitly published final release even
            # when the browse surface has moved its current pointer to a newer
            # markdown preview. A preview is useful for exploration, but it has
            # no reviewed theory profiles and cannot silently become M4 input.
            if purpose is KnowledgeUsePurpose.MATCH:
                row = session.scalar(
                    select(KnowledgeReleaseRow)
                    .where(KnowledgeReleaseRow.level == KnowledgeReleaseLevel.FINAL.value)
                    .order_by(KnowledgeReleaseRow.built_at.desc())
                )
            else:
                row = session.scalar(
                    select(KnowledgeReleaseRow)
                    .where(
                        KnowledgeReleaseRow.is_current.is_(True),
                        KnowledgeReleaseRow.level.in_(
                            [
                                KnowledgeReleaseLevel.PREVIEW.value,
                                KnowledgeReleaseLevel.FINAL.value,
                            ]
                        ),
                        or_(
                            KnowledgeReleaseRow.level == KnowledgeReleaseLevel.FINAL.value,
                            KnowledgeReleaseRow.build_config_version == _BUILD_CONFIG_VERSION,
                        ),
                    )
                    .order_by(KnowledgeReleaseRow.built_at.desc())
                )
            if row is None:
                row = self._publish_preview(session)
            return _release_ref(row)

    def browse(
        self,
        *,
        release_id: str,
        query: str | None,
        category: str | None,
        category_id: str | None,
        dimension_id: str | None,
        cursor: str | None,
        limit: int,
    ) -> KnowledgeEntryPage:
        with self._database.session() as session:
            release = _require_release(session, release_id)
            normalized_query = query.strip() if query and query.strip() else None
            cursor_scope = _browse_cursor_scope(
                release_id=release_id,
                query=normalized_query,
                category=category,
                category_id=category_id,
                dimension_id=dimension_id,
            )
            offset = _decode_cursor(cursor, cursor_scope) if cursor else 0
            statement = select(KnowledgeEntryRevisionRow).where(
                KnowledgeEntryRevisionRow.knowledge_release_id == release_id,
                KnowledgeEntryRevisionRow.browse_eligible.is_(True),
            )
            if category is not None:
                statement = statement.where(KnowledgeEntryRevisionRow.category == category)
            if category_id is not None:
                statement = statement.where(
                    KnowledgeEntryRevisionRow.category_id == category_id
                )
            if dimension_id is not None:
                statement = statement.where(
                    KnowledgeEntryRevisionRow.dimension_id == dimension_id
                )
            if normalized_query:
                matching_ids = _matching_ids(session, release_id, normalized_query)
                if not matching_ids:
                    return KnowledgeEntryPage(
                        release=_release_ref(release),
                        entries=(),
                        total_count=0,
                        next_cursor=None,
                    )
                statement = statement.where(
                    KnowledgeEntryRevisionRow.knowledge_id.in_(matching_ids)
                )

            total_count = int(
                session.scalar(select(func.count()).select_from(statement.subquery())) or 0
            )
            if offset > total_count:
                raise ValueError("invalid knowledge cursor")
            rows = list(
                session.scalars(
                    statement.order_by(KnowledgeEntryRevisionRow.knowledge_id)
                    .offset(offset)
                    .limit(limit)
                )
            )
            next_cursor = (
                _encode_cursor(cursor_scope, offset + limit)
                if offset + limit < total_count
                else None
            )
            return KnowledgeEntryPage(
                release=_release_ref(release),
                entries=tuple(_entry_summary(row) for row in rows),
                total_count=total_count,
                next_cursor=next_cursor,
            )

    def get_directory(self, *, release_id: str) -> KnowledgeDirectorySummary:
        with self._database.session() as session:
            release = _require_release(session, release_id)
            facets: dict[str, dict[str, object]] = {
                f"D{index}": {
                    "node_type": KnowledgeDirectoryNodeType.DIMENSION,
                    "title": title,
                    "parent_node_id": None,
                    "entry_count": 0,
                }
                for index, title in enumerate(_DIMENSION_DIRECTORIES, start=1)
            }
            rows = tuple(
                session.execute(
                select(
                    KnowledgeEntryRevisionRow.directory_path,
                    KnowledgeEntryRevisionRow.title,
                )
                .where(
                    KnowledgeEntryRevisionRow.knowledge_release_id == release_id,
                    KnowledgeEntryRevisionRow.browse_eligible.is_(True),
                )
                .order_by(KnowledgeEntryRevisionRow.knowledge_id)
                )
            )
            terminal_counts: dict[str, int] = {}
            node_occurrences: dict[str, int] = {}
            for path, _entry_title in rows:
                for raw_node in path:
                    node_id = raw_node["node_id"]
                    node_occurrences[node_id] = node_occurrences.get(node_id, 0) + 1
                if path:
                    terminal_id = path[-1]["node_id"]
                    terminal_counts[terminal_id] = terminal_counts.get(terminal_id, 0) + 1
            for path, entry_title in rows:
                parent_node_id: str | None = None
                for index, raw_node in enumerate(path):
                    node_id = raw_node["node_id"]
                    node_type = KnowledgeDirectoryNodeType(raw_node["node_type"])
                    # The imported hierarchy's final label can lag behind the entry
                    # it points to. Directory leaves represent browse destinations,
                    # so expose the immutable entry title while preserving node IDs.
                    title = (
                        entry_title
                        if index == len(path) - 1
                        and terminal_counts[node_id] == 1
                        and node_occurrences[node_id] == 1
                        else raw_node["title"]
                    )
                    existing = facets.get(node_id)
                    if existing is None:
                        existing = {
                            "node_type": node_type,
                            "title": title,
                            "parent_node_id": parent_node_id,
                            "entry_count": 0,
                        }
                        facets[node_id] = existing
                    elif (
                        existing["node_type"] != node_type
                        or existing["title"] != title
                        or existing["parent_node_id"] != parent_node_id
                    ):
                        raise ValueError(f"inconsistent directory node: {node_id}")
                    existing["entry_count"] = int(existing["entry_count"]) + 1
                    parent_node_id = node_id

            return KnowledgeDirectorySummary(
                release=_release_ref(release),
                nodes=tuple(
                    KnowledgeDirectoryFacetSnapshot(
                        node_id=node_id,
                        node_type=facet["node_type"],
                        title=str(facet["title"]),
                        parent_node_id=facet["parent_node_id"],
                        entry_count=int(facet["entry_count"]),
                    )
                    for node_id, facet in facets.items()
                ),
            )

    def get_entry(
        self,
        *,
        knowledge_id: str,
        release_id: str,
    ) -> KnowledgeEntryDetail:
        with self._database.session() as session:
            release = _require_release(session, release_id)
            row = session.scalar(
                select(KnowledgeEntryRevisionRow).where(
                    KnowledgeEntryRevisionRow.knowledge_release_id == release_id,
                    KnowledgeEntryRevisionRow.knowledge_id == knowledge_id,
                    KnowledgeEntryRevisionRow.browse_eligible.is_(True),
                )
            )
            if row is None:
                raise LookupError(knowledge_id)
            source_rows = session.scalars(
                select(KnowledgeSourceRow)
                .where(KnowledgeSourceRow.knowledge_release_id == release_id)
                .where(KnowledgeSourceRow.source_id == f"source:{knowledge_id}")
                .order_by(KnowledgeSourceRow.source_id)
            )
            relation_rows = session.scalars(
                select(KnowledgeRelationRow)
                .where(KnowledgeRelationRow.knowledge_release_id == release_id)
                .where(KnowledgeRelationRow.review_status == KnowledgeReviewStatus.REVIEWED.value)
                .where(
                    or_(
                        KnowledgeRelationRow.source_knowledge_id == knowledge_id,
                        KnowledgeRelationRow.target_knowledge_id == knowledge_id,
                    )
                )
                .order_by(KnowledgeRelationRow.relation_id)
            )
            theory_row = session.scalar(
                select(KnowledgeTheoryProfileRow).where(
                    KnowledgeTheoryProfileRow.knowledge_release_id == release_id,
                    KnowledgeTheoryProfileRow.related_knowledge_ids.contains([knowledge_id]),
                )
            )
            return KnowledgeEntryDetail(
                release=_release_ref(release),
                summary=_entry_summary(row),
                aliases=tuple(row.aliases),
                content=row.content,
                sources=tuple(_source_snapshot(source) for source in source_rows),
                relations=tuple(_relation_snapshot(relation) for relation in relation_rows),
                theory_profile=(
                    _theory_profile_snapshot(theory_row) if theory_row is not None else None
                ),
            )

    def get_theory_profile(
        self,
        *,
        theory_id: str,
        release_id: str,
    ) -> TheoryProfileSnapshot:
        with self._database.session() as session:
            _require_release(session, release_id)
            row = session.scalar(
                select(KnowledgeTheoryProfileRow).where(
                    KnowledgeTheoryProfileRow.knowledge_release_id == release_id,
                    KnowledgeTheoryProfileRow.theory_id == theory_id,
                )
            )
            if row is None:
                raise LookupError(theory_id)
            return _theory_profile_snapshot(row)

    def get_sources(
        self,
        *,
        source_ids: tuple[str, ...],
        release_id: str,
    ) -> tuple[SourceRecordSnapshot, ...]:
        with self._database.session() as session:
            _require_release(session, release_id)
            rows = session.scalars(
                select(KnowledgeSourceRow)
                .where(KnowledgeSourceRow.knowledge_release_id == release_id)
                .where(KnowledgeSourceRow.source_id.in_(source_ids))
                .order_by(KnowledgeSourceRow.source_id)
            )
            return tuple(_source_snapshot(row) for row in rows)

    def list_connections(
        self,
        *,
        release_id: str,
        source_node_id: str | None,
        cursor: str | None,
        limit: int,
    ) -> StructuralConnectionPage:
        with self._database.session() as session:
            release = _require_release(session, release_id)
            cursor_scope = f"{release_id}|connections|{source_node_id or '*'}"
            offset = _decode_cursor(cursor, cursor_scope) if cursor else 0
            rows = tuple(
                session.scalars(
                    select(KnowledgeEntryRevisionRow)
                    .where(
                        KnowledgeEntryRevisionRow.knowledge_release_id == release_id,
                        KnowledgeEntryRevisionRow.browse_eligible.is_(True),
                    )
                    .order_by(KnowledgeEntryRevisionRow.knowledge_id)
                )
            )
            connections = build_structural_connections(
                tuple(_structural_input(row) for row in rows)
            )
            if source_node_id:
                connections = tuple(
                    item for item in connections if item.source_node_id == source_node_id
                )
            page = connections[offset : offset + limit]
            next_cursor = (
                _encode_cursor(cursor_scope, offset + limit)
                if offset + limit < len(connections)
                else None
            )
            return StructuralConnectionPage(
                release=_release_ref(release),
                connections=tuple(_connection_snapshot(item) for item in page),
                total_count=len(connections),
                next_cursor=next_cursor,
            )

    def list_relation_candidates(
        self,
        *,
        release_id: str,
        knowledge_id: str | None,
        cursor: str | None,
        limit: int,
    ) -> RelationCandidatePage:
        with self._database.session() as session:
            release = _require_release(session, release_id)
            cursor_scope = f"{release_id}|candidates|{knowledge_id or '*'}"
            offset = _decode_cursor(cursor, cursor_scope) if cursor else 0
            filters = [
                KnowledgeRelationCandidateRow.knowledge_release_id == release_id
            ]
            if knowledge_id:
                filters.append(
                    or_(
                        KnowledgeRelationCandidateRow.source_knowledge_id
                        == knowledge_id,
                        KnowledgeRelationCandidateRow.target_knowledge_id
                        == knowledge_id,
                    )
                )
            total_count = session.scalar(
                select(func.count())
                .select_from(KnowledgeRelationCandidateRow)
                .where(*filters)
            )
            rows = session.scalars(
                select(KnowledgeRelationCandidateRow)
                .where(*filters)
                .order_by(KnowledgeRelationCandidateRow.candidate_id)
                .offset(offset)
                .limit(limit)
            )
            count = int(total_count or 0)
            return RelationCandidatePage(
                release=_release_ref(release),
                candidates=tuple(_candidate_snapshot(row) for row in rows),
                total_count=count,
                next_cursor=(
                    _encode_cursor(cursor_scope, offset + limit)
                    if offset + limit < count
                    else None
                ),
            )

    def list_relations(
        self,
        *,
        release_id: str,
        knowledge_id: str | None,
        cursor: str | None,
        limit: int,
    ) -> KnowledgeRelationPage:
        with self._database.session() as session:
            release = _require_release(session, release_id)
            cursor_scope = f"{release_id}|relations|{knowledge_id or '*'}"
            offset = _decode_cursor(cursor, cursor_scope) if cursor else 0
            reviewed = KnowledgeRelationRow.review_status == KnowledgeReviewStatus.REVIEWED.value
            filters = [
                KnowledgeRelationRow.knowledge_release_id == release_id,
                reviewed,
            ]
            if knowledge_id:
                filters.append(
                    or_(
                        KnowledgeRelationRow.source_knowledge_id == knowledge_id,
                        KnowledgeRelationRow.target_knowledge_id == knowledge_id,
                    )
                )
            total_count = session.scalar(
                select(func.count())
                .select_from(KnowledgeRelationRow)
                .where(*filters)
            )
            rows = session.scalars(
                select(KnowledgeRelationRow)
                .where(*filters)
                .order_by(KnowledgeRelationRow.relation_id)
                .offset(offset)
                .limit(limit)
            )
            count = int(total_count or 0)
            return KnowledgeRelationPage(
                release=_release_ref(release),
                relations=tuple(_relation_snapshot(row) for row in rows),
                total_count=count,
                next_cursor=(
                    _encode_cursor(cursor_scope, offset + limit)
                    if offset + limit < count
                    else None
                ),
            )

    def get_manifest(self, release_id: str) -> KnowledgeReleaseManifest:
        with self._database.session() as session:
            return _manifest(_require_release(session, release_id))

    def _publish_preview(self, session: object) -> KnowledgeReleaseRow:
        imported_entries = _imported_entries(self._knowledge_root)
        content_hash = _release_hash(imported_entries)
        existing = session.scalar(
            select(KnowledgeReleaseRow).where(KnowledgeReleaseRow.content_hash == content_hash)
        )
        if existing is not None:
            session.execute(
                update(KnowledgeReleaseRow)
                .where(KnowledgeReleaseRow.level == KnowledgeReleaseLevel.PREVIEW.value)
                .values(is_current=False)
            )
            existing.is_current = True
            return existing

        content_versions = {}
        for imported in imported_entries:
            previous = session.scalar(
                select(KnowledgeEntryRevisionRow)
                .where(KnowledgeEntryRevisionRow.knowledge_id == imported.entry.knowledge_id)
                .order_by(KnowledgeEntryRevisionRow.content_version.desc())
            )
            content_versions[imported.entry.knowledge_id] = (
                1
                if previous is None
                else previous.content_version
                if previous.content_hash == imported.content_hash
                else previous.content_version + 1
            )
        candidate_inputs = tuple(
            RelationCandidateInput(
                knowledge_id=item.entry.knowledge_id,
                title=item.entry.title,
                content=item.entry.content,
                source_path=item.source_path,
                content_version=content_versions[item.entry.knowledge_id],
            )
            for item in imported_entries
        )
        candidates = extract_relation_candidates(candidate_inputs)
        structural_connection_count = len(
            build_structural_connections(
                tuple(
                    StructuralConnectionInput(
                        knowledge_id=item.entry.knowledge_id,
                        title=item.entry.title,
                        directory_path=tuple(
                            StructuralNodeInput(
                                node_id=node.node_id,
                                node_type=node.node_type.value,
                                title=node.title,
                            )
                            for node in item.entry.directory_path
                        ),
                    )
                    for item in imported_entries
                )
            )
        )
        release_id = f"knowledge-preview-{content_hash.removeprefix('sha256:')}"
        now = datetime.now(UTC)
        manifest = {
            "knowledge_ids": [item.entry.knowledge_id for item in imported_entries],
            "relation_candidate_ids": [item.candidate_id for item in candidates],
            "relation_ids": [],
            "structural_connection_count": structural_connection_count,
            "theory_ids": [],
            "source_ids": [f"source:{item.entry.knowledge_id}" for item in imported_entries],
            "review_record_ids": [],
            "artifact_hashes": [
                ["parser_config", _BUILD_CONFIG_VERSION],
                ["relation_candidate_config", PRODUCER_CONFIG_VERSION],
            ],
        }
        session.execute(
            update(KnowledgeReleaseRow)
            .where(KnowledgeReleaseRow.level == KnowledgeReleaseLevel.PREVIEW.value)
            .values(is_current=False)
        )
        release = KnowledgeReleaseRow(
            knowledge_release_id=release_id,
            level=KnowledgeReleaseLevel.PREVIEW.value,
            content_hash=content_hash,
            build_config_version=_BUILD_CONFIG_VERSION,
            manifest=manifest,
            is_current=True,
            built_at=now,
        )
        session.add(release)
        session.flush()
        for imported in imported_entries:
            entry = imported.entry
            content_version = content_versions[entry.knowledge_id]
            category_node = entry.directory_path[-1] if len(entry.directory_path) > 1 else None
            session.add(
                KnowledgeEntryRevisionRow(
                    knowledge_release_id=release_id,
                    knowledge_id=entry.knowledge_id,
                    content_version=content_version,
                    content_hash=imported.content_hash,
                    title=entry.title,
                    category_id=category_node.node_id if category_node is not None else None,
                    category=category_node.title if category_node is not None else None,
                    dimension_id=entry.directory_path[0].node_id,
                    dimension=entry.directory_path[0].title,
                    directory_path=[
                        {
                            "node_id": node.node_id,
                            "node_type": node.node_type.value,
                            "title": node.title,
                        }
                        for node in entry.directory_path
                    ],
                    review_status=KnowledgeReviewStatus.PENDING.value,
                    browse_eligible=True,
                    rag_eligible=False,
                    training_candidate_eligible=False,
                    match_eligible=False,
                    review_record_ids=[],
                    aliases=[],
                    content=entry.content,
                    source_path=imported.source_path,
                    source_hash=imported.source_hash,
                )
            )
            session.add(
                KnowledgeSourceRow(
                    knowledge_release_id=release_id,
                    source_id=f"source:{entry.knowledge_id}",
                    source_type="repository_markdown",
                    title=imported.source_path,
                    authors_or_institution=["群学致知知识库"],
                    year=None,
                    publication="repository Markdown source",
                    locator=f"{imported.source_path}#{entry.knowledge_id}",
                    url=None,
                    verification_status=SourceVerificationStatus.PENDING.value,
                    use_boundary=_PREVIEW_SOURCE_BOUNDARY,
                )
            )
        for candidate in candidates:
            session.add(
                KnowledgeRelationCandidateRow(
                    knowledge_release_id=release_id,
                    candidate_id=candidate.candidate_id,
                    source_knowledge_id=candidate.source_knowledge_id,
                    target_knowledge_id=candidate.target_knowledge_id,
                    suggested_relation_type=candidate.suggested_relation_type,
                    direction=candidate.direction,
                    evidence_excerpt=candidate.evidence_excerpt,
                    evidence_locator=candidate.evidence_locator,
                    evidence_source_id=candidate.evidence_source_id,
                    source_content_version=candidate.source_content_version,
                    target_content_version=candidate.target_content_version,
                    producer=candidate.producer,
                    producer_config_version=candidate.producer_config_version,
                    score=candidate.score,
                    trigger_reason=candidate.trigger_reason,
                    review_status=candidate.review_status,
                    review_record_id=None,
                )
            )
        session.flush()
        session.execute(
            text(
                "INSERT INTO knowledge_search_fts "
                "(knowledge_release_id, knowledge_id, title, content, category, dimension) "
                "VALUES (:knowledge_release_id, :knowledge_id, :title, :content, "
                ":category, :dimension)"
            ),
            [
                {
                    "knowledge_release_id": release_id,
                    "knowledge_id": item.entry.knowledge_id,
                    "title": item.entry.title,
                    "content": item.entry.content,
                    "category": item.entry.directory_path[-1].title,
                    "dimension": item.entry.directory_path[0].title,
                }
                for item in imported_entries
            ],
        )
        return release


def _imported_entries(knowledge_root: Path) -> tuple[_ImportedEntry, ...]:
    imported = []
    seen_ids: set[str] = set()
    for dimension in _DIMENSION_DIRECTORIES:
        for source_path in sorted((knowledge_root / dimension).glob("*.md")):
            source_bytes = source_path.read_bytes()
            markdown = source_bytes.decode("utf-8")
            source_hash = f"sha256:{sha256(source_bytes).hexdigest()}"
            for entry in parse_knowledge_markdown(source_path, markdown):
                if entry.knowledge_id in seen_ids:
                    raise ValueError(f"Duplicate knowledge id: {entry.knowledge_id}")
                seen_ids.add(entry.knowledge_id)
                imported.append(
                    _ImportedEntry(
                        entry=entry,
                        source_path=source_path.relative_to(knowledge_root).as_posix(),
                        source_hash=source_hash,
                        content_hash=_hash(entry.content),
                    )
                )
    return tuple(sorted(imported, key=lambda item: item.entry.knowledge_id))


def _release_hash(imported_entries: tuple[_ImportedEntry, ...]) -> str:
    payload = {
        "build_config_version": _BUILD_CONFIG_VERSION,
        "relation_candidate_config_version": PRODUCER_CONFIG_VERSION,
        "entries": [
            {
                "knowledge_id": item.entry.knowledge_id,
                "title": item.entry.title,
                "directory_path": [
                    {
                        "node_id": node.node_id,
                        "node_type": node.node_type.value,
                        "title": node.title,
                    }
                    for node in item.entry.directory_path
                ],
                "content_hash": item.content_hash,
                "source_path": item.source_path,
                "source_hash": item.source_hash,
            }
            for item in imported_entries
        ],
    }
    return _hash(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def _hash(value: str) -> str:
    return f"sha256:{sha256(value.encode()).hexdigest()}"


def _browse_cursor_scope(
    *,
    release_id: str,
    query: str | None,
    category: str | None,
    category_id: str | None,
    dimension_id: str | None,
) -> str:
    filters = json.dumps(
        {
            "query": query,
            "category": category,
            "category_id": category_id,
            "dimension_id": dimension_id,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"{release_id}|entries|{sha256(filters.encode()).hexdigest()}"


def _require_release(session: object, release_id: str) -> KnowledgeReleaseRow:
    row = session.get(KnowledgeReleaseRow, release_id)
    if row is None or row.level == KnowledgeReleaseLevel.WORKING.value:
        raise LookupError(release_id)
    return row


def _matching_ids(session: object, release_id: str, query: str) -> tuple[str, ...]:
    if len(query) < 3:
        rows = session.scalars(
            select(KnowledgeEntryRevisionRow.knowledge_id).where(
                KnowledgeEntryRevisionRow.knowledge_release_id == release_id,
                or_(
                    func.instr(KnowledgeEntryRevisionRow.knowledge_id, query) > 0,
                    func.instr(KnowledgeEntryRevisionRow.title, query) > 0,
                    func.instr(KnowledgeEntryRevisionRow.content, query) > 0,
                    func.instr(KnowledgeEntryRevisionRow.category, query) > 0,
                    func.instr(KnowledgeEntryRevisionRow.dimension, query) > 0,
                ),
            )
        )
        return tuple(rows)
    escaped_query = query.replace('"', '""')
    phrase = f'"{escaped_query}"'
    rows = session.execute(
        text(
            "SELECT knowledge_id FROM knowledge_search_fts "
            "WHERE knowledge_release_id = :knowledge_release_id "
            "AND knowledge_search_fts MATCH :query"
        ),
        {"knowledge_release_id": release_id, "query": phrase},
    ).scalars()
    return tuple(rows)


def _entry_summary(row: KnowledgeEntryRevisionRow) -> KnowledgeEntrySummary:
    return KnowledgeEntrySummary(
        knowledge_id=row.knowledge_id,
        content_version=row.content_version,
        title=row.title,
        category_id=row.category_id or row.dimension_id,
        category=row.category or row.dimension,
        dimension_id=row.dimension_id,
        dimension=row.dimension,
        directory_path=tuple(
            KnowledgeDirectoryNodeSnapshot(
                node_id=node["node_id"],
                node_type=KnowledgeDirectoryNodeType(node["node_type"]),
                title=node["title"],
            )
            for node in row.directory_path
        ),
        review_status=KnowledgeReviewStatus(row.review_status),
        eligibility=KnowledgeUseEligibility(
            browse_eligible=row.browse_eligible,
            rag_eligible=row.rag_eligible,
            training_candidate_eligible=row.training_candidate_eligible,
            match_eligible=row.match_eligible,
            review_record_ids=tuple(row.review_record_ids),
        ),
    )


def _structural_input(row: KnowledgeEntryRevisionRow) -> StructuralConnectionInput:
    return StructuralConnectionInput(
        knowledge_id=row.knowledge_id,
        title=row.title,
        directory_path=tuple(
            StructuralNodeInput(
                node_id=node["node_id"],
                node_type=node["node_type"],
                title=node["title"],
            )
            for node in row.directory_path
        ),
    )


def _connection_snapshot(item: object) -> StructuralConnectionSnapshot:
    return StructuralConnectionSnapshot(
        connection_id=item.connection_id,
        source_node_id=item.source_node_id,
        source_node_type=item.source_node_type,
        source_title=item.source_title,
        target_node_id=item.target_node_id,
        target_node_type=item.target_node_type,
        target_title=item.target_title,
        connection_type=item.connection_type,
        direction=item.direction,
    )


def _candidate_snapshot(row: KnowledgeRelationCandidateRow) -> RelationCandidateSnapshot:
    return RelationCandidateSnapshot(
        candidate_id=row.candidate_id,
        source_knowledge_id=row.source_knowledge_id,
        target_knowledge_id=row.target_knowledge_id,
        suggested_relation_type=row.suggested_relation_type,
        direction=row.direction,
        evidence_excerpt=row.evidence_excerpt,
        evidence_locator=row.evidence_locator,
        evidence_source_id=row.evidence_source_id,
        source_content_version=row.source_content_version,
        target_content_version=row.target_content_version,
        producer=row.producer,
        producer_config_version=row.producer_config_version,
        score=row.score,
        trigger_reason=row.trigger_reason,
        review_status=KnowledgeReviewStatus(row.review_status),
        review_record_id=row.review_record_id,
    )


def _source_snapshot(row: KnowledgeSourceRow) -> SourceRecordSnapshot:
    return SourceRecordSnapshot(
        source_id=row.source_id,
        source_type=row.source_type,
        title=row.title,
        authors_or_institution=tuple(row.authors_or_institution),
        year=row.year,
        publication=row.publication,
        locator=row.locator,
        url=row.url,
        verification_status=SourceVerificationStatus(row.verification_status),
        use_boundary=row.use_boundary,
    )


def _relation_snapshot(row: KnowledgeRelationRow) -> KnowledgeRelationSnapshot:
    return KnowledgeRelationSnapshot(
        relation_id=row.relation_id,
        source_knowledge_id=row.source_knowledge_id,
        target_knowledge_id=row.target_knowledge_id,
        relation_type=row.relation_type,
        direction=row.direction,
        description=row.description,
        evidence_source_ids=tuple(row.evidence_source_ids),
        evidence_grade=row.evidence_grade,
        content_version=row.content_version,
        review_status=KnowledgeReviewStatus(row.review_status),
    )


def _theory_profile_snapshot(row: KnowledgeTheoryProfileRow) -> TheoryProfileSnapshot:
    return TheoryProfileSnapshot(
        theory_id=row.theory_id,
        related_knowledge_ids=tuple(row.related_knowledge_ids),
        title=row.title,
        core_propositions=tuple(row.core_propositions),
        applicable_phenomena=tuple(row.applicable_phenomena),
        analysis_levels=tuple(row.analysis_levels),
        prerequisites=tuple(row.prerequisites),
        exclusion_signals=tuple(row.exclusion_signals),
        observable_evidence=tuple(row.observable_evidence),
        competing_or_complementary_theory_ids=tuple(
            row.competing_or_complementary_theory_ids
        ),
        source_ids=tuple(row.source_ids),
        content_version=row.content_version,
        review_status=KnowledgeReviewStatus(row.review_status),
        match_eligible=row.match_eligible,
    )


def _release_ref(row: KnowledgeReleaseRow) -> KnowledgeReleaseRef:
    return KnowledgeReleaseRef(
        knowledge_release_id=row.knowledge_release_id,
        level=KnowledgeReleaseLevel(row.level),
        content_hash=row.content_hash,
    )


def _manifest(row: KnowledgeReleaseRow) -> KnowledgeReleaseManifest:
    return KnowledgeReleaseManifest(
        release=_release_ref(row),
        knowledge_ids=tuple(row.manifest["knowledge_ids"]),
        relation_candidate_ids=tuple(row.manifest.get("relation_candidate_ids", [])),
        relation_ids=tuple(row.manifest["relation_ids"]),
        structural_connection_count=int(row.manifest.get("structural_connection_count", 0)),
        theory_ids=tuple(row.manifest["theory_ids"]),
        source_ids=tuple(row.manifest["source_ids"]),
        review_record_ids=tuple(row.manifest["review_record_ids"]),
        artifact_hashes=tuple(tuple(item) for item in row.manifest["artifact_hashes"]),
        built_at=row.built_at.replace(tzinfo=UTC)
        if row.built_at.tzinfo is None
        else row.built_at,
    )


def _encode_cursor(release_id: str, offset: int) -> str:
    return urlsafe_b64encode(f"{release_id}:{offset}".encode()).decode().rstrip("=")


def _decode_cursor(cursor: str, release_id: str) -> int:
    try:
        padding = "=" * (-len(cursor) % 4)
        value = urlsafe_b64decode(f"{cursor}{padding}").decode()
        cursor_release_id, raw_offset = value.rsplit(":", maxsplit=1)
        offset = int(raw_offset)
        if cursor_release_id != release_id or offset < 0:
            raise ValueError
        return offset
    except (UnicodeDecodeError, ValueError) as error:
        raise ValueError("invalid knowledge cursor") from error
