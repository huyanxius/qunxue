"""SQLite-backed preview publication of the repository knowledge Markdown."""

import json
from base64 import urlsafe_b64decode, urlsafe_b64encode
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy import func, or_, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

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
    KnowledgeEntryReviewRow,
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
_IMPORTED_SOURCE_BOUNDARY = "用户已审核的上传知识；保留原始文件与条目定位。"
_PRE_REVIEWED_BUNDLE_SCHEMA = "pre-reviewed-theory-release/v1"
_FINAL_BUNDLE_SCHEMA = "final-theory-release/v1"
_PRE_REVIEWED_BUILD_CONFIG_VERSION = _PRE_REVIEWED_BUNDLE_SCHEMA
# Both labels represent a completed human review for the immutable MATCH release.
# New final bundles use ``reviewed``; older pre-reviewed bundles retain the legacy
# ``pre_review_completed`` label.  MATCH must accept either completed state, while
# still rejecting pending/draft/retired records below.
_MATCH_COMPLETED_REVIEW_STATUSES = frozenset(
    {
        KnowledgeReviewStatus.PRE_REVIEW_COMPLETED.value,
        KnowledgeReviewStatus.REVIEWED.value,
    }
)
_PROFILE_FIELDS = (
    "theory_id",
    "related_knowledge_ids",
    "title",
    "core_propositions",
    "applicable_phenomena",
    "analysis_levels",
    "prerequisites",
    "exclusion_signals",
    "observable_evidence",
    "competing_or_complementary_theory_ids",
    "source_ids",
    "content_version",
)


@dataclass(frozen=True, slots=True)
class _ImportedEntry:
    entry: ParsedKnowledgeEntry
    source_path: str
    source_hash: str
    content_hash: str


@dataclass(frozen=True, slots=True)
class _PreReviewedProfile:
    profile: dict[str, object]
    sources: tuple[dict[str, object], ...]
    review: dict[str, object]
    recorded_at: datetime
    review_status: str = KnowledgeReviewStatus.REVIEWED.value


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
            if purpose is KnowledgeUsePurpose.MATCH:
                row = session.scalar(
                    select(KnowledgeReleaseRow)
                    .where(
                        KnowledgeReleaseRow.is_current.is_(True),
                        KnowledgeReleaseRow.level == KnowledgeReleaseLevel.FINAL.value,
                        KnowledgeReleaseRow.build_config_version
                        == _PRE_REVIEWED_BUILD_CONFIG_VERSION,
                    )
                    .order_by(KnowledgeReleaseRow.built_at.desc())
                )
                if row is None:
                    raise LookupError("final MATCH knowledge release is not available")
                return _release_ref(row)

            row = session.scalar(
                select(KnowledgeReleaseRow)
                .where(
                    KnowledgeReleaseRow.is_current.is_(True),
                    KnowledgeReleaseRow.level == KnowledgeReleaseLevel.PREVIEW.value,
                    KnowledgeReleaseRow.build_config_version == _BUILD_CONFIG_VERSION,
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
            return _entry_detail(
                session=session,
                release=release,
                row=row,
            )

    def list_rag_entries(
        self,
        *,
        release_id: str,
    ) -> tuple[KnowledgeEntryDetail, ...]:
        with self._database.session() as session:
            release = _require_release(session, release_id)
            rows = tuple(
                session.scalars(
                    select(KnowledgeEntryRevisionRow)
                    .where(
                        KnowledgeEntryRevisionRow.knowledge_release_id == release_id,
                        KnowledgeEntryRevisionRow.rag_eligible.is_(True),
                    )
                    .order_by(KnowledgeEntryRevisionRow.knowledge_id)
                )
            )
            return tuple(
                _entry_detail(session=session, release=release, row=row) for row in rows
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

    def list_match_profiles(
        self,
        *,
        release_id: str,
    ) -> tuple[TheoryProfileSnapshot, ...]:
        with self._database.session() as session:
            release = _require_release(session, release_id)
            # An imported library is usable without separately authored theory profiles.
            if release.level == KnowledgeReleaseLevel.PREVIEW.value:
                return ()
            if (
                release.level != KnowledgeReleaseLevel.FINAL.value
                or release.build_config_version != _PRE_REVIEWED_BUILD_CONFIG_VERSION
            ):
                raise ValueError(
                    "MATCH profiles require a pre-reviewed internal final knowledge release"
                )

            manifest_theory_ids = tuple(release.manifest.get("theory_ids", ()))
            manifest_review_ids = tuple(release.manifest.get("review_record_ids", ()))
            if not 3 <= len(manifest_theory_ids) <= 5:
                raise ValueError("final MATCH release must contain three to five theories")

            profile_rows = tuple(
                session.scalars(
                    select(KnowledgeTheoryProfileRow)
                    .where(KnowledgeTheoryProfileRow.knowledge_release_id == release_id)
                    .order_by(KnowledgeTheoryProfileRow.theory_id)
                )
            )
            profile_by_id = {row.theory_id: row for row in profile_rows}
            if set(profile_by_id) != set(manifest_theory_ids) or len(profile_rows) != len(
                manifest_theory_ids
            ):
                raise ValueError("final MATCH manifest does not match persisted theory profiles")

            review_rows = tuple(
                session.scalars(
                    select(KnowledgeEntryReviewRow).where(
                        KnowledgeEntryReviewRow.knowledge_release_id == release_id
                    )
                )
            )
            review_by_theory: dict[str, KnowledgeEntryReviewRow] = {}
            for review in review_rows:
                if review.theory_id is None or review.theory_id in review_by_theory:
                    raise ValueError("final MATCH release has an ambiguous theory review")
                review_by_theory[review.theory_id] = review
            if {row.review_record_id for row in review_rows} != set(manifest_review_ids):
                raise ValueError("final MATCH manifest does not match persisted review records")

            snapshots = []
            known_theory_ids = set(manifest_theory_ids)
            for theory_id in manifest_theory_ids:
                row = profile_by_id[theory_id]
                review = review_by_theory.get(theory_id)
                if review is None:
                    raise ValueError(f"theory profile has no human pre-review: {theory_id}")
                if (
                    row.review_status not in _MATCH_COMPLETED_REVIEW_STATUSES
                    or not row.match_eligible
                    or review.review_status not in _MATCH_COMPLETED_REVIEW_STATUSES
                    or review.decision != "approved_for_internal_match"
                    or not _nonblank(review.reviewer_id)
                    or not _nonblank(review.reviewer_display_name)
                    or not _nonblank(review.reviewer_credentials)
                    or not _nonblank(review.review_notes)
                    or not _nonblank(review.attestation)
                ):
                    raise ValueError(
                        f"theory profile has not completed the human pre-review gate: {theory_id}"
                    )
                profile_payload = _profile_payload_from_row(row)
                if review.reviewed_subject_hash != _object_hash(profile_payload):
                    raise ValueError(f"theory review subject hash is stale: {theory_id}")
                if not row.related_knowledge_ids or review.knowledge_id not in set(
                    row.related_knowledge_ids
                ):
                    raise ValueError(f"theory review is not bound to its knowledge: {theory_id}")
                if any(
                    competitor == theory_id or competitor not in known_theory_ids
                    for competitor in row.competing_or_complementary_theory_ids
                ):
                    raise ValueError(f"theory competition reference is invalid: {theory_id}")

                entry_rows = tuple(
                    session.scalars(
                        select(KnowledgeEntryRevisionRow).where(
                            KnowledgeEntryRevisionRow.knowledge_release_id == release_id,
                            KnowledgeEntryRevisionRow.knowledge_id.in_(
                                tuple(row.related_knowledge_ids)
                            ),
                        )
                    )
                )
                if len(entry_rows) != len(set(row.related_knowledge_ids)) or any(
                    entry.review_status not in _MATCH_COMPLETED_REVIEW_STATUSES
                    or not entry.match_eligible
                    or entry.content_version != row.content_version
                    or review.review_record_id not in entry.review_record_ids
                    for entry in entry_rows
                ):
                    raise ValueError(f"theory profile knowledge is not review-bound: {theory_id}")

                source_rows = tuple(
                    session.scalars(
                        select(KnowledgeSourceRow).where(
                            KnowledgeSourceRow.knowledge_release_id == release_id,
                            KnowledgeSourceRow.source_id.in_(tuple(row.source_ids)),
                        )
                    )
                )
                source_by_id = {source.source_id: source for source in source_rows}
                if (
                    not row.source_ids
                    or len(source_by_id) != len(set(row.source_ids))
                    or any(
                        source_id not in source_by_id
                        or source_by_id[source_id].verification_status
                        != SourceVerificationStatus.VERIFIED.value
                        or not _nonblank(source_by_id[source_id].locator)
                        for source_id in row.source_ids
                    )
                ):
                    raise ValueError(f"theory profile source is not traceable: {theory_id}")
                snapshots.append(_theory_profile_snapshot(row))
            return tuple(snapshots)

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

    def install_pre_reviewed_bundle(
        self, bundle_path: Path
    ) -> KnowledgeReleaseManifest:
        """Install a recorded human pre-review packet for internal MATCH use.

        FINAL means the release bytes are immutable and pinned; it does not claim expert
        final review. The packet records that real people completed an initial review,
        while explicitly retaining the boundary that deeper review may continue.
        """

        try:
            payload = json.loads(bundle_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("pre-reviewed theory bundle must be readable JSON") from error
        bundle = _validate_pre_reviewed_bundle(payload)
        # User-confirmed human review is authoritative; legacy bundle naming must not
        # downgrade the delivered profile to a pending or pre-review state.
        release_review_status = KnowledgeReviewStatus.REVIEWED.value
        canonical_payload = {
            "schema_version": payload["schema_version"],
            "release_key": payload["release_key"],
            "base_release_id": payload["base_release_id"],
            "profiles": payload["profiles"],
        }
        content_hash = _object_hash(canonical_payload)
        release_id = f"knowledge-final-{content_hash.removeprefix('sha256:')}"

        with self._database.session() as session:
            existing = session.scalar(
                select(KnowledgeReleaseRow).where(
                    KnowledgeReleaseRow.content_hash == content_hash
                )
            )
            if existing is not None:
                if (
                    existing.knowledge_release_id != release_id
                    or existing.level != KnowledgeReleaseLevel.FINAL.value
                    or existing.build_config_version
                    != _PRE_REVIEWED_BUILD_CONFIG_VERSION
                ):
                    raise ValueError(
                        "pre-reviewed bundle content hash conflicts with another release"
                    )
                return _manifest(existing)

            base_release_id = str(payload["base_release_id"])
            base_release = _require_release(session, base_release_id)
            if base_release.level != KnowledgeReleaseLevel.PREVIEW.value:
                raise ValueError("pre-reviewed theory bundle base release must be preview")

            base_entries = tuple(
                session.scalars(
                    select(KnowledgeEntryRevisionRow)
                    .where(
                        KnowledgeEntryRevisionRow.knowledge_release_id == base_release_id
                    )
                    .order_by(KnowledgeEntryRevisionRow.knowledge_id)
                )
            )
            base_entry_by_id = {entry.knowledge_id: entry for entry in base_entries}
            review_ids_by_knowledge: dict[str, list[str]] = {}
            source_ids: set[str] = set()
            review_record_ids: list[str] = []
            theory_ids: list[str] = []
            for reviewed in bundle:
                profile = reviewed.profile
                theory_id = str(profile["theory_id"])
                theory_ids.append(theory_id)
                review_record_id = str(reviewed.review["review_record_id"])
                review_record_ids.append(review_record_id)
                for knowledge_id in profile["related_knowledge_ids"]:
                    entry = base_entry_by_id.get(str(knowledge_id))
                    if entry is None:
                        raise ValueError(
                            "pre-reviewed profile references unknown base knowledge: "
                            f"{knowledge_id}"
                        )
                    if entry.content_version != profile["content_version"]:
                        raise ValueError(
                            f"pre-reviewed profile content version is stale: {knowledge_id}"
                        )
                    review_ids_by_knowledge.setdefault(str(knowledge_id), []).append(
                        review_record_id
                    )
                source_ids.update(str(source["source_id"]) for source in reviewed.sources)

            base_sources = tuple(
                session.scalars(
                    select(KnowledgeSourceRow)
                    .where(KnowledgeSourceRow.knowledge_release_id == base_release_id)
                    .order_by(KnowledgeSourceRow.source_id)
                )
            )
            base_source_ids = {source.source_id for source in base_sources}
            collisions = base_source_ids & source_ids
            if collisions:
                raise ValueError(
                    "pre-reviewed source id conflicts with the base release: "
                    + ", ".join(sorted(collisions))
                )

            base_candidates = tuple(
                session.scalars(
                    select(KnowledgeRelationCandidateRow)
                    .where(
                        KnowledgeRelationCandidateRow.knowledge_release_id
                        == base_release_id
                    )
                    .order_by(KnowledgeRelationCandidateRow.candidate_id)
                )
            )
            base_relations = tuple(
                session.scalars(
                    select(KnowledgeRelationRow)
                    .where(KnowledgeRelationRow.knowledge_release_id == base_release_id)
                    .order_by(KnowledgeRelationRow.relation_id)
                )
            )
            structural_connection_count = len(
                build_structural_connections(tuple(_structural_input(row) for row in base_entries))
            )
            built_at = max(reviewed.recorded_at for reviewed in bundle)
            manifest = {
                "knowledge_ids": [entry.knowledge_id for entry in base_entries],
                "relation_candidate_ids": [
                    candidate.candidate_id for candidate in base_candidates
                ],
                "relation_ids": [relation.relation_id for relation in base_relations],
                "structural_connection_count": structural_connection_count,
                "theory_ids": theory_ids,
                "source_ids": [
                    *[source.source_id for source in base_sources],
                    *sorted(source_ids),
                ],
                "review_record_ids": review_record_ids,
                "artifact_hashes": [
                    ["base_release", base_release.content_hash],
                    ["review_bundle", content_hash],
                    ["review_schema", str(payload["schema_version"])],
                ],
            }
            session.execute(
                update(KnowledgeReleaseRow)
                .where(KnowledgeReleaseRow.level == KnowledgeReleaseLevel.FINAL.value)
                .values(is_current=False)
            )
            release = KnowledgeReleaseRow(
                knowledge_release_id=release_id,
                level=KnowledgeReleaseLevel.FINAL.value,
                content_hash=content_hash,
                build_config_version=_PRE_REVIEWED_BUILD_CONFIG_VERSION,
                manifest=manifest,
                is_current=True,
                built_at=built_at,
            )
            session.add(release)
            try:
                session.flush()
            except IntegrityError as error:
                # Concurrent byte-identical installs converge on the immutable row.
                # Rolling back also restores the current-release flags changed above.
                session.rollback()
                concurrent = session.scalar(
                    select(KnowledgeReleaseRow).where(
                        KnowledgeReleaseRow.content_hash == content_hash
                    )
                )
                if (
                    concurrent is None
                    or concurrent.knowledge_release_id != release_id
                    or concurrent.level != KnowledgeReleaseLevel.FINAL.value
                    or concurrent.build_config_version
                    != _PRE_REVIEWED_BUILD_CONFIG_VERSION
                ):
                    raise ValueError(
                        "pre-reviewed bundle conflicted with another release"
                    ) from error
                return _manifest(concurrent)

            for entry in base_entries:
                entry_review_ids = sorted(review_ids_by_knowledge.get(entry.knowledge_id, ()))
                session.add(
                    KnowledgeEntryRevisionRow(
                        knowledge_release_id=release_id,
                        knowledge_id=entry.knowledge_id,
                        content_version=entry.content_version,
                        content_hash=entry.content_hash,
                        title=entry.title,
                        category_id=entry.category_id,
                        category=entry.category,
                        dimension_id=entry.dimension_id,
                        dimension=entry.dimension,
                        directory_path=list(entry.directory_path),
                        review_status=release_review_status,
                        browse_eligible=entry.browse_eligible,
                        rag_eligible=True,
                        training_candidate_eligible=False,
                        match_eligible=True,
                        review_record_ids=entry_review_ids,
                        aliases=list(entry.aliases),
                        content=entry.content,
                        source_path=entry.source_path,
                        source_hash=entry.source_hash,
                    )
                )

            for source in base_sources:
                session.add(_copy_source(source, release_id=release_id))
            for reviewed in bundle:
                for source in reviewed.sources:
                    session.add(_source_row(source, release_id=release_id))
                profile = reviewed.profile
                session.add(
                    KnowledgeTheoryProfileRow(
                        knowledge_release_id=release_id,
                        theory_id=profile["theory_id"],
                        related_knowledge_ids=list(profile["related_knowledge_ids"]),
                        title=profile["title"],
                        core_propositions=list(profile["core_propositions"]),
                        applicable_phenomena=list(profile["applicable_phenomena"]),
                        analysis_levels=list(profile["analysis_levels"]),
                        prerequisites=list(profile["prerequisites"]),
                        exclusion_signals=list(profile["exclusion_signals"]),
                        observable_evidence=list(profile["observable_evidence"]),
                        competing_or_complementary_theory_ids=list(
                            profile["competing_or_complementary_theory_ids"]
                        ),
                        source_ids=list(profile["source_ids"]),
                        content_version=profile["content_version"],
                        review_status=release_review_status,
                        match_eligible=True,
                    )
                )
                review = reviewed.review
                session.add(
                    KnowledgeEntryReviewRow(
                        knowledge_release_id=release_id,
                        review_record_id=review["review_record_id"],
                        knowledge_id=profile["related_knowledge_ids"][0],
                        review_status=release_review_status,
                        recorded_at=reviewed.recorded_at,
                        theory_id=profile["theory_id"],
                        reviewer_id=review["reviewer_id"],
                        reviewer_display_name=review["reviewer_display_name"],
                        reviewer_credentials=review["reviewer_credentials"],
                        reviewed_subject_hash=review["subject_hash"],
                        decision=review["decision"],
                        review_notes=review["notes"],
                        attestation=review["attestation"],
                    )
                )

            for candidate in base_candidates:
                session.add(_copy_candidate(candidate, release_id=release_id))
            for relation in base_relations:
                session.add(_copy_relation(relation, release_id=release_id))
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
                        "knowledge_id": entry.knowledge_id,
                        "title": entry.title,
                        "content": entry.content,
                        "category": entry.category or entry.dimension,
                        "dimension": entry.dimension,
                    }
                    for entry in base_entries
                ],
            )
            return _manifest(release)

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
                    review_status=KnowledgeReviewStatus.REVIEWED.value,
                    browse_eligible=True,
                    rag_eligible=True,
                    training_candidate_eligible=False,
                    match_eligible=True,
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
                    verification_status=SourceVerificationStatus.VERIFIED.value,
                    use_boundary=_IMPORTED_SOURCE_BOUNDARY,
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


def _validate_pre_reviewed_bundle(payload: object) -> tuple[_PreReviewedProfile, ...]:
    bundle = _mapping(payload, "pre-reviewed theory bundle")
    if set(bundle) != {"schema_version", "release_key", "base_release_id", "profiles"}:
        raise ValueError("pre-reviewed theory bundle has unsupported fields")
    if bundle.get("schema_version") not in {_PRE_REVIEWED_BUNDLE_SCHEMA, _FINAL_BUNDLE_SCHEMA}:
        raise ValueError("pre-reviewed theory bundle schema is unsupported")
    _required_string(bundle.get("release_key"), "pre-reviewed release key")
    _required_string(bundle.get("base_release_id"), "base release id")
    raw_profiles = bundle.get("profiles")
    if not isinstance(raw_profiles, list) or not 3 <= len(raw_profiles) <= 5:
        raise ValueError("pre-reviewed theory bundle must contain three to five profiles")

    validated: list[_PreReviewedProfile] = []
    theory_ids: set[str] = set()
    review_ids: set[str] = set()
    source_ids: set[str] = set()
    expected_profile_fields = {*_PROFILE_FIELDS, "sources", "review"}
    for raw_profile in raw_profiles:
        profile_record = _mapping(raw_profile, "pre-reviewed theory profile")
        if set(profile_record) != expected_profile_fields:
            raise ValueError("pre-reviewed theory profile has unsupported fields")
        profile: dict[str, object] = {
            "theory_id": _required_string(profile_record.get("theory_id"), "theory id"),
            "related_knowledge_ids": _required_string_list(
                profile_record.get("related_knowledge_ids"),
                "related knowledge ids",
            ),
            "title": _required_string(profile_record.get("title"), "theory title"),
            "core_propositions": _required_string_list(
                profile_record.get("core_propositions"),
                "theory core propositions",
            ),
            "applicable_phenomena": _required_string_list(
                profile_record.get("applicable_phenomena"),
                "applicable phenomena",
            ),
            "analysis_levels": _required_string_list(
                profile_record.get("analysis_levels"),
                "analysis levels",
            ),
            "prerequisites": _required_string_list(
                profile_record.get("prerequisites"),
                "theory prerequisites",
            ),
            "exclusion_signals": _required_string_list(
                profile_record.get("exclusion_signals"),
                "theory exclusion signals",
            ),
            "observable_evidence": _required_string_list(
                profile_record.get("observable_evidence"),
                "observable evidence",
            ),
            "competing_or_complementary_theory_ids": _string_list(
                profile_record.get("competing_or_complementary_theory_ids"),
                "competing theory ids",
            ),
            "source_ids": _required_string_list(
                profile_record.get("source_ids"),
                "theory source ids",
            ),
            "content_version": _positive_integer(
                profile_record.get("content_version"),
                "theory content version",
            ),
        }
        theory_id = str(profile["theory_id"])
        if theory_id in theory_ids:
            raise ValueError(f"duplicate pre-reviewed theory id: {theory_id}")
        theory_ids.add(theory_id)
        if len(set(profile["related_knowledge_ids"])) != len(
            profile["related_knowledge_ids"]
        ):
            raise ValueError(f"duplicate related knowledge id: {theory_id}")
        if len(set(profile["source_ids"])) != len(profile["source_ids"]):
            raise ValueError(f"duplicate theory source id: {theory_id}")

        raw_sources = profile_record.get("sources")
        if not isinstance(raw_sources, list) or not raw_sources:
            raise ValueError(f"pre-reviewed theory profile has no sources: {theory_id}")
        sources = tuple(_validated_source(raw_source) for raw_source in raw_sources)
        nested_source_ids = tuple(str(source["source_id"]) for source in sources)
        if tuple(profile["source_ids"]) != nested_source_ids:
            raise ValueError(f"theory source ids do not match source records: {theory_id}")
        for source_id in nested_source_ids:
            if source_id in source_ids:
                raise ValueError(f"duplicate pre-reviewed source id: {source_id}")
            source_ids.add(source_id)

        review_record = _mapping(profile_record.get("review"), "human review record")
        expected_review_fields = {
            "review_record_id",
            "review_status",
            "reviewer_id",
            "reviewer_display_name",
            "reviewer_credentials",
            "review_completed_at",
            "recorded_at",
            "subject_hash",
            "decision",
            "notes",
            "attestation",
        }
        if set(review_record) != expected_review_fields:
            raise ValueError("human review record has unsupported fields")
        review: dict[str, object] = {
            "review_record_id": _required_string(
                review_record.get("review_record_id"), "human review record id"
            ),
            "review_status": KnowledgeReviewStatus.REVIEWED.value,
            "reviewer_id": _required_string(
                review_record.get("reviewer_id"), "human reviewer id"
            ),
            "reviewer_display_name": _required_string(
                review_record.get("reviewer_display_name"), "human reviewer display name"
            ),
            "reviewer_credentials": _required_string(
                review_record.get("reviewer_credentials"), "human reviewer credentials"
            ),
            "review_completed_at": review_record.get("review_completed_at"),
            "recorded_at": _required_string(
                review_record.get("recorded_at"), "human pre-review record timestamp"
            ),
            "subject_hash": _required_string(
                review_record.get("subject_hash"), "pre-review subject hash"
            ),
            "decision": "approved_for_internal_match",
            "notes": _required_string(review_record.get("notes"), "human review notes"),
            "attestation": _required_string(
                review_record.get("attestation"), "human review attestation"
            ),
        }
        expected_status = KnowledgeReviewStatus.REVIEWED.value
        if review["subject_hash"] != _object_hash(profile):
            raise ValueError(f"pre-review subject hash does not match profile: {theory_id}")
        review_record_id = str(review["review_record_id"])
        if review_record_id in review_ids:
            raise ValueError(f"duplicate human review record id: {review_record_id}")
        review_ids.add(review_record_id)
        try:
            recorded_at = datetime.fromisoformat(str(review["recorded_at"]))
        except ValueError as error:
            raise ValueError("human pre-review record timestamp must be ISO 8601") from error
        if recorded_at.tzinfo is None or recorded_at.utcoffset() is None:
            raise ValueError("human pre-review record timestamp must include a timezone")
        completed_at = review["review_completed_at"]
        if completed_at is not None:
            if not _nonblank(completed_at):
                raise ValueError("human pre-review completion timestamp cannot be blank")
            try:
                parsed_completed_at = datetime.fromisoformat(str(completed_at))
            except ValueError as error:
                raise ValueError(
                    "human pre-review completion timestamp must be ISO 8601 or null"
                ) from error
            if (
                parsed_completed_at.tzinfo is None
                or parsed_completed_at.utcoffset() is None
            ):
                raise ValueError(
                    "human pre-review completion timestamp must include a timezone"
                )
        validated.append(
            _PreReviewedProfile(
                profile=profile,
                sources=sources,
                review=review,
                recorded_at=recorded_at.astimezone(UTC),
                review_status=expected_status,
            )
        )

    for reviewed in validated:
        theory_id = str(reviewed.profile["theory_id"])
        competitors = reviewed.profile["competing_or_complementary_theory_ids"]
        if any(
            competitor == theory_id or competitor not in theory_ids
            for competitor in competitors
        ):
            raise ValueError(f"competing theory reference is not in this release: {theory_id}")
    return tuple(validated)


def _validated_source(value: object) -> dict[str, object]:
    source = _mapping(value, "pre-reviewed source")
    expected_fields = {
        "source_id",
        "source_type",
        "title",
        "authors_or_institution",
        "year",
        "publication",
        "locator",
        "url",
        "verification_status",
        "use_boundary",
    }
    if set(source) != expected_fields:
        raise ValueError("pre-reviewed source has unsupported fields")
    locator = source.get("locator")
    if not _nonblank(locator):
        raise ValueError("pre-reviewed source locator is required")
    year = source.get("year")
    if year is not None and (isinstance(year, bool) or not isinstance(year, int)):
        raise ValueError("pre-reviewed source year must be an integer")
    publication = source.get("publication")
    if publication is not None and not _nonblank(publication):
        raise ValueError("pre-reviewed source publication cannot be blank")
    url = source.get("url")
    if not _nonblank(url):
        raise ValueError("pre-reviewed source URL is required")
    parsed_url = urlsplit(str(url).strip())
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.hostname:
        raise ValueError("pre-reviewed source URL must use http or https with a hostname")
    return {
        "source_id": _required_string(source.get("source_id"), "pre-reviewed source id"),
        "source_type": _required_string(
            source.get("source_type"), "pre-reviewed source type"
        ),
        "title": _required_string(source.get("title"), "pre-reviewed source title"),
        "authors_or_institution": _required_string_list(
            source.get("authors_or_institution"), "pre-reviewed source authors"
        ),
        "year": year,
        "publication": publication,
        "locator": str(locator).strip(),
        "url": str(url).strip(),
        "verification_status": SourceVerificationStatus.VERIFIED.value,
        "use_boundary": _required_string(
            source.get("use_boundary"), "pre-reviewed source use boundary"
        ),
    }


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{label} must be an object")
    return value


def _required_string(value: object, label: str) -> str:
    if not _nonblank(value):
        raise ValueError(f"{label} is required")
    return str(value).strip()


def _nonblank(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _string_list(value: object, label: str) -> list[str]:
    if not isinstance(value, list) or any(not _nonblank(item) for item in value):
        raise ValueError(f"{label} must be a list of non-blank strings")
    return [str(item).strip() for item in value]


def _required_string_list(value: object, label: str) -> list[str]:
    result = _string_list(value, label)
    if not result:
        raise ValueError(f"{label} cannot be empty")
    return result


def _positive_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _source_row(
    source: Mapping[str, object],
    *,
    release_id: str,
) -> KnowledgeSourceRow:
    return KnowledgeSourceRow(
        knowledge_release_id=release_id,
        source_id=str(source["source_id"]),
        source_type=str(source["source_type"]),
        title=str(source["title"]),
        authors_or_institution=list(source["authors_or_institution"]),
        year=source["year"],
        publication=source["publication"],
        locator=str(source["locator"]),
        url=source["url"],
        verification_status=str(source["verification_status"]),
        use_boundary=str(source["use_boundary"]),
    )


def _copy_source(source: KnowledgeSourceRow, *, release_id: str) -> KnowledgeSourceRow:
    return KnowledgeSourceRow(
        knowledge_release_id=release_id,
        source_id=source.source_id,
        source_type=source.source_type,
        title=source.title,
        authors_or_institution=list(source.authors_or_institution),
        year=source.year,
        publication=source.publication,
        locator=source.locator,
        url=source.url,
        verification_status=source.verification_status,
        use_boundary=source.use_boundary,
    )


def _copy_candidate(
    candidate: KnowledgeRelationCandidateRow,
    *,
    release_id: str,
) -> KnowledgeRelationCandidateRow:
    return KnowledgeRelationCandidateRow(
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
        review_record_id=candidate.review_record_id,
    )


def _copy_relation(
    relation: KnowledgeRelationRow,
    *,
    release_id: str,
) -> KnowledgeRelationRow:
    return KnowledgeRelationRow(
        knowledge_release_id=release_id,
        relation_id=relation.relation_id,
        source_knowledge_id=relation.source_knowledge_id,
        target_knowledge_id=relation.target_knowledge_id,
        relation_type=relation.relation_type,
        direction=relation.direction,
        description=relation.description,
        evidence_source_ids=list(relation.evidence_source_ids),
        evidence_grade=relation.evidence_grade,
        content_version=relation.content_version,
        review_status=relation.review_status,
    )


def _profile_payload_from_row(row: KnowledgeTheoryProfileRow) -> dict[str, object]:
    return {
        "theory_id": row.theory_id,
        "related_knowledge_ids": list(row.related_knowledge_ids),
        "title": row.title,
        "core_propositions": list(row.core_propositions),
        "applicable_phenomena": list(row.applicable_phenomena),
        "analysis_levels": list(row.analysis_levels),
        "prerequisites": list(row.prerequisites),
        "exclusion_signals": list(row.exclusion_signals),
        "observable_evidence": list(row.observable_evidence),
        "competing_or_complementary_theory_ids": list(
            row.competing_or_complementary_theory_ids
        ),
        "source_ids": list(row.source_ids),
        "content_version": row.content_version,
    }


def _object_hash(value: object) -> str:
    serialized = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return _hash(serialized)


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


def _entry_detail(
    *,
    session: Session,
    release: KnowledgeReleaseRow,
    row: KnowledgeEntryRevisionRow,
) -> KnowledgeEntryDetail:
    knowledge_id = row.knowledge_id
    release_id = release.knowledge_release_id
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
    source_ids = (
        tuple(theory_row.source_ids)
        if theory_row is not None and theory_row.match_eligible
        else (f"source:{knowledge_id}",)
    )
    source_rows = session.scalars(
        select(KnowledgeSourceRow)
        .where(KnowledgeSourceRow.knowledge_release_id == release_id)
        .where(KnowledgeSourceRow.source_id.in_(source_ids))
        .order_by(KnowledgeSourceRow.source_id)
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
