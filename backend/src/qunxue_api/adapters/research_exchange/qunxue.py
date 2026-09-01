"""Explicit mapping from published module snapshots to REFI-QDA Project 1.0."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from enum import Enum
from uuid import UUID

from qunxue_api.modules.research_analysis import (
    AnalysisAnnotation,
    AnalysisCode,
    AnalysisCodeStatus,
    AnalysisMemo,
    CodebookEntry,
)
from qunxue_api.modules.research_exchange import (
    ExchangeIdentity,
    ExchangeLoss,
    ExchangeLossSeverity,
    ExchangeReport,
    QdpxCase,
    QdpxCode,
    QdpxCoding,
    QdpxLink,
    QdpxMemo,
    QdpxProject,
    QdpxSelection,
    QdpxSet,
    QdpxSource,
    QdpxSourceKind,
    QdpxUser,
)
from qunxue_api.modules.research_intake import ResearchTask
from qunxue_api.modules.research_materials import (
    MaterialFormat,
    MaterialParseVersion,
    MaterialStatus,
    ProfessionalMaterialArchive,
    ResearchMaterial,
)


@dataclass(frozen=True, slots=True)
class QunxueResearchProjectSnapshot:
    """Read-only adapter input assembled by the application composition layer."""

    task: ResearchTask
    materials: tuple[ResearchMaterial, ...]
    parses: tuple[MaterialParseVersion, ...]
    archive: ProfessionalMaterialArchive
    annotations: tuple[AnalysisAnnotation, ...]
    codes: tuple[AnalysisCode, ...]
    memos: tuple[AnalysisMemo, ...]
    codebook_entries: tuple[CodebookEntry, ...]
    original_contents: dict[UUID, bytes] | None = None
    extension_snapshots: dict[str, object] | None = None


@dataclass(frozen=True, slots=True)
class QunxueQdpxMapping:
    project: QdpxProject
    report: ExchangeReport
    recovery_manifest: dict[str, object]


def map_published_qunxue_project(
    *,
    task: ResearchTask,
    materials: tuple[ResearchMaterial, ...],
    parses: tuple[MaterialParseVersion, ...],
    archive: ProfessionalMaterialArchive,
    annotations: tuple[AnalysisAnnotation, ...],
    codes: tuple[AnalysisCode, ...],
    memos: tuple[AnalysisMemo, ...],
    codebook_entries: tuple[CodebookEntry, ...],
    original_contents: dict[UUID, bytes],
    extension_snapshots: dict[str, object],
) -> QunxueQdpxMapping:
    """Adapt published module values without exposing adapter DTOs upstream."""

    return map_to_qdpx(
        QunxueResearchProjectSnapshot(
            task=task,
            materials=materials,
            parses=parses,
            archive=archive,
            annotations=annotations,
            codes=codes,
            memos=memos,
            codebook_entries=codebook_entries,
            original_contents=original_contents,
            extension_snapshots=extension_snapshots,
        )
    )


def _jsonable(value: object) -> object:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return value


def _snapshot(value: object) -> dict[str, object]:
    rendered = _jsonable(asdict(value))
    assert isinstance(rendered, dict)
    return rendered


def _loss(
    *,
    object_type: str,
    object_id: UUID | str,
    field: str,
    reason: str,
    disposition: str = "recovery_manifest",
    severity: ExchangeLossSeverity = ExchangeLossSeverity.WARNING,
) -> ExchangeLoss:
    return ExchangeLoss(
        object_type=object_type,
        object_id=str(object_id),
        field=field,
        reason=reason,
        disposition=disposition,
        severity=severity,
    )


def _source_text(
    material: ResearchMaterial,
    parse: MaterialParseVersion | None,
    originals: dict[UUID, bytes],
) -> tuple[str | None, dict[str, int], tuple[ExchangeLoss, ...]]:
    if parse is not None:
        offsets: dict[str, int] = {}
        cursor = 0
        chunks: list[str] = []
        for block in parse.blocks:
            offsets[block.segment_id] = cursor
            chunks.append(block.text)
            cursor += len(block.text) + 2
        return "\n\n".join(chunks), offsets, ()
    content = originals.get(material.material_id)
    if material.material_format in {MaterialFormat.TXT, MaterialFormat.MARKDOWN} and content:
        try:
            return content.decode("utf-8"), {}, ()
        except UnicodeDecodeError:
            pass
    return (
        None,
        {},
        (
            _loss(
                object_type="material",
                object_id=material.material_id,
                field="content",
                reason="no proven UTF-8 text or current parse is available for QDPX",
                disposition="omitted",
                severity=ExchangeLossSeverity.BLOCKING,
            ),
        ),
    )


def map_to_qdpx(snapshot: QunxueResearchProjectSnapshot) -> QunxueQdpxMapping:
    task = snapshot.task
    for collection in (
        snapshot.materials,
        snapshot.parses,
        snapshot.annotations,
        snapshot.codes,
        snapshot.memos,
        snapshot.codebook_entries,
    ):
        for value in collection:
            if getattr(value, "task_id", task.task_id) != task.task_id:
                raise ValueError("exchange snapshot contains another research task")

    losses: list[ExchangeLoss] = []
    losses.append(
        _loss(
            object_type="research_task",
            object_id=task.task_id,
            field="task_id",
            reason="REFI-QDA Project 1.0 has no project GUID field",
        )
    )
    parse_by_id = {value.parse_id: value for value in snapshot.parses}
    annotations_by_material: dict[UUID, list[AnalysisAnnotation]] = {}
    for annotation in snapshot.annotations:
        annotations_by_material.setdefault(annotation.material_id, []).append(annotation)
    confirmed_codes = tuple(
        code for code in snapshot.codes if code.status is AnalysisCodeStatus.CONFIRMED
    )
    confirmed_code_ids = {code.code_id for code in confirmed_codes}
    codebook_by_code = {entry.code_id: entry for entry in snapshot.codebook_entries}
    memo_by_annotation: dict[UUID, list[UUID]] = {}
    memo_by_code: dict[UUID, list[UUID]] = {}
    for memo in snapshot.memos:
        for annotation_id in memo.annotation_ids:
            memo_by_annotation.setdefault(annotation_id, []).append(memo.memo_id)
        for code_id in memo.code_ids:
            memo_by_code.setdefault(code_id, []).append(memo.memo_id)
        losses.extend(
            (
                _loss(
                    object_type="analysis_memo",
                    object_id=memo.memo_id,
                    field="status",
                    reason="REFI-QDA Note has no candidate or confirmation state",
                ),
                _loss(
                    object_type="analysis_memo",
                    object_id=memo.memo_id,
                    field="version",
                    reason="REFI-QDA Note has no native version history",
                ),
            )
        )

    qdpx_codes: list[QdpxCode] = []
    for code in snapshot.codes:
        if code.code_id not in confirmed_code_ids:
            losses.append(
                _loss(
                    object_type="analysis_code",
                    object_id=code.code_id,
                    field="status",
                    reason="unconfirmed analysis codes are not exported as formal QDPX codes",
                    disposition="omitted",
                )
            )
            continue
        codebook = codebook_by_code.get(code.code_id)
        parent_code_id = codebook.parent_code_id if codebook else None
        if parent_code_id is not None and parent_code_id not in confirmed_code_ids:
            losses.append(
                _loss(
                    object_type="codebook_entry",
                    object_id=code.code_id,
                    field="parent_code_id",
                    reason="the parent code is not a confirmed exported code",
                    disposition="flattened",
                )
            )
            parent_code_id = None
        qdpx_codes.append(
            QdpxCode(
                code_id=code.code_id,
                name=code.label,
                description=code.definition,
                parent_code_id=parent_code_id,
                memo_ids=tuple(memo_by_code.get(code.code_id, ())),
            )
        )
        losses.append(
            _loss(
                object_type="analysis_code",
                object_id=code.code_id,
                field="version",
                reason="REFI-QDA Code has no native version history",
            )
        )
        if codebook is not None:
            losses.append(
                _loss(
                    object_type="codebook_entry",
                    object_id=code.code_id,
                    field="rules_and_examples",
                    reason="REFI-QDA Code cannot preserve structured codebook rules and examples",
                )
            )

    originals = snapshot.original_contents or {}
    qdpx_sources: list[QdpxSource] = []
    for material in snapshot.materials:
        if material.status is MaterialStatus.DELETED:
            losses.append(
                _loss(
                    object_type="material",
                    object_id=material.material_id,
                    field="deleted_at",
                    reason="deleted source content is not exported",
                    disposition="tombstone_only",
                )
            )
            continue
        parse = (
            parse_by_id.get(material.current_parse_id)
            if material.current_parse_id is not None
            else None
        )
        source_text, segment_offsets, source_losses = _source_text(material, parse, originals)
        losses.extend(source_losses)
        if source_text is None:
            continue
        if material.material_format.is_media:
            losses.append(
                _loss(
                    object_type="material",
                    object_id=material.material_id,
                    field="media_payload",
                    reason=(
                        "the published transcript is exported as a QDPX text source; "
                        "the original media payload remains in the native archive"
                    ),
                )
            )
            if parse is not None and any(
                block.locator.time_start_ms is not None or block.locator.speaker is not None
                for block in parse.blocks
            ):
                losses.append(
                    _loss(
                        object_type="material_parse",
                        object_id=parse.parse_id,
                        field="timecodes_and_speakers",
                        reason=(
                            "plain-text QDPX selections do not preserve transcript "
                            "timecodes or speaker labels"
                        ),
                    )
                )
        selections: list[QdpxSelection] = []
        for annotation in annotations_by_material.get(material.material_id, ()):
            if not annotation.source_available or annotation.parse_id != material.current_parse_id:
                losses.append(
                    _loss(
                        object_type="analysis_annotation",
                        object_id=annotation.annotation_id,
                        field="source_version",
                        reason="annotation is tombstoned or not pinned to the exported parse",
                        disposition="omitted",
                        severity=ExchangeLossSeverity.BLOCKING,
                    )
                )
                continue
            base = segment_offsets.get(annotation.segment_id)
            if base is None:
                losses.append(
                    _loss(
                        object_type="analysis_annotation",
                        object_id=annotation.annotation_id,
                        field="segment_id",
                        reason="the pinned source segment is absent from the exported parse",
                        disposition="omitted",
                        severity=ExchangeLossSeverity.BLOCKING,
                    )
                )
                continue
            start = base + annotation.quote_start
            end = base + annotation.quote_end
            if source_text[start:end] != annotation.quote:
                losses.append(
                    _loss(
                        object_type="analysis_annotation",
                        object_id=annotation.annotation_id,
                        field="quote_range",
                        reason="the stored quote does not match the pinned source range",
                        disposition="omitted",
                        severity=ExchangeLossSeverity.BLOCKING,
                    )
                )
                continue
            codings = tuple(
                QdpxCoding(coding_id=code.code_id, code_id=code.code_id, user_id=task.user_id)
                for code in confirmed_codes
                if annotation.annotation_id in code.annotation_ids
            )
            selections.append(
                QdpxSelection(
                    selection_id=annotation.annotation_id,
                    name=annotation.note,
                    start_position=start,
                    end_position=end,
                    codings=codings,
                    memo_ids=tuple(memo_by_annotation.get(annotation.annotation_id, ())),
                )
            )
        qdpx_sources.append(
            QdpxSource(
                source_id=material.material_id,
                name=material.display_name,
                kind=QdpxSourceKind.TEXT,
                plain_text=source_text,
                selections=tuple(selections),
                user_id=task.user_id,
            )
        )
        if parse is not None:
            losses.append(
                _loss(
                    object_type="material_parse",
                    object_id=parse.parse_id,
                    field="version",
                    reason="REFI-QDA Source has no native parse-version identity",
                )
            )

    qdpx_cases = tuple(
        QdpxCase(
            case_id=case.case_id,
            name=case.name,
            description=case.description,
            attributes=case.attributes,
            source_ids=tuple(
                material_id
                for material_id in case.material_ids
                if any(source.source_id == material_id for source in qdpx_sources)
            ),
            selection_ids=tuple(
                annotation.annotation_id
                for annotation in snapshot.annotations
                if annotation.case_label == case.name
                and any(
                    annotation.annotation_id == selection.selection_id
                    for source in qdpx_sources
                    for selection in source.selections
                )
            ),
        )
        for case in snapshot.archive.cases
    )
    qdpx_sets = tuple(
        QdpxSet(
            set_id=collection.collection_id,
            name=collection.name,
            description=collection.description,
            member_source_ids=tuple(
                profile.material_id
                for profile in snapshot.archive.profiles
                if collection.collection_id in profile.collection_ids
                and any(source.source_id == profile.material_id for source in qdpx_sources)
            ),
        )
        for collection in snapshot.archive.collections
    )
    qdpx_links = tuple(
        QdpxLink(
            link_id=relation.relation_id,
            name=relation.relation_type.value,
            origin_id=relation.source_material_id,
            target_id=relation.target_material_id,
        )
        for relation in snapshot.archive.relations
        if all(
            any(source.source_id == material_id for source in qdpx_sources)
            for material_id in (relation.source_material_id, relation.target_material_id)
        )
    )
    for relation in snapshot.archive.relations:
        if relation.note:
            losses.append(
                _loss(
                    object_type="material_relation",
                    object_id=relation.relation_id,
                    field="note",
                    reason="REFI-QDA Link has no inline description",
                )
            )

    project = QdpxProject(
        project_id=task.task_id,
        name=task.project_title,
        origin="群学致知",
        description=task.phenomenon_summary,
        users=(QdpxUser(user_id=task.user_id, name="群学致知研究者"),),
        codes=tuple(qdpx_codes),
        sources=tuple(qdpx_sources),
        memos=tuple(
            QdpxMemo(
                memo_id=memo.memo_id,
                name=memo.title,
                content=memo.content,
                target_ids=tuple((*memo.annotation_ids, *memo.code_ids)),
                user_id=task.user_id,
            )
            for memo in snapshot.memos
        ),
        cases=qdpx_cases,
        sets=qdpx_sets,
        links=qdpx_links,
    )
    recovery_manifest: dict[str, object] = {
        "schema_version": "qunxue-research-project-archive-v1",
        "task": _snapshot(task),
        "materials": {
            "records": [_snapshot(value) for value in snapshot.materials],
            "parses": [_snapshot(value) for value in snapshot.parses],
            "professional_archive": _snapshot(snapshot.archive),
        },
        "analysis": {
            "annotations": [_snapshot(value) for value in snapshot.annotations],
            "codes": [_snapshot(value) for value in snapshot.codes],
            "memos": [_snapshot(value) for value in snapshot.memos],
            "codebook_entries": [_snapshot(value) for value in snapshot.codebook_entries],
        },
        "extensions": _jsonable(snapshot.extension_snapshots or {}),
    }
    for extension_name, extension_value in sorted(
        (snapshot.extension_snapshots or {}).items()
    ):
        if extension_value in (None, (), [], {}, ""):
            continue
        losses.append(
            _loss(
                object_type="research_project_extension",
                object_id=task.task_id,
                field=extension_name,
                reason="the published Qunxue contract has no REFI-QDA Project 1.0 representation",
            )
        )
    identities = tuple(
        ExchangeIdentity(object_type=object_type, native_id=str(value), exchange_guid=value)
        for object_type, value in (
            *(("material", item.source_id) for item in project.sources),
            *(("analysis_code", item.code_id) for item in project.codes),
            *(("analysis_memo", item.memo_id) for item in project.memos),
            *(("research_case", item.case_id) for item in project.cases),
            *(("material_collection", item.set_id) for item in project.sets),
            *(("material_relation", item.link_id) for item in project.links),
            *(
                ("analysis_annotation", selection.selection_id)
                for source in project.sources
                for selection in source.selections
            ),
        )
    )
    return QunxueQdpxMapping(
        project=project,
        report=ExchangeReport(losses=tuple(losses), identities=identities),
        recovery_manifest=recovery_manifest,
    )
