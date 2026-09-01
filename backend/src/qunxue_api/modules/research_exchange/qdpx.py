"""Deterministic REFI-QDA Project 1.0 import, export, and XSD validation."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from functools import lru_cache
from io import BytesIO
from pathlib import Path, PurePosixPath
from uuid import UUID, uuid5
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile, ZipInfo

import xmlschema

from qunxue_api.modules.research_exchange.model import (
    ExchangeLoss,
    ExchangeLossSeverity,
    ExchangeReport,
    QdpxCase,
    QdpxCode,
    QdpxCoding,
    QdpxLink,
    QdpxMemo,
    QdpxProject,
    QdpxScalar,
    QdpxSelection,
    QdpxSet,
    QdpxSource,
    QdpxSourceKind,
    QdpxUser,
)

QDPX_NAMESPACE = "urn:QDA-XML:project:1.0"
_VARIABLE_NAMESPACE = UUID("bb082df7-f7dc-5c20-b64b-5d1c8b13dc07")
_MAX_ARCHIVE_MEMBERS = 10_000
_MAX_ARCHIVE_BYTES = 2 * 1024 * 1024 * 1024
_MAX_PROJECT_XML_BYTES = 100 * 1024 * 1024
_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
_REFI_TIMESTAMP = "1970-01-01T00:00:00Z"

ET.register_namespace("", QDPX_NAMESPACE)


@dataclass(frozen=True, slots=True)
class QdpxValidation:
    valid: bool
    errors: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class QdpxExport:
    payload: bytes
    sha256: str
    report: ExchangeReport


@dataclass(frozen=True, slots=True)
class QdpxImport:
    project: QdpxProject
    report: ExchangeReport


def _q(name: str) -> str:
    return f"{{{QDPX_NAMESPACE}}}{name}"


def _element(parent: ET.Element, tag: str, **attributes: object) -> ET.Element:
    return ET.SubElement(
        parent,
        _q(tag),
        {key: str(value) for key, value in attributes.items() if value is not None},
    )


def _text(parent: ET.Element, name: str, value: str | None) -> ET.Element | None:
    if value is None:
        return None
    child = _element(parent, name)
    child.text = value
    return child


def _note_refs(parent: ET.Element, memo_ids: tuple[UUID, ...]) -> None:
    for memo_id in memo_ids:
        _element(parent, "NoteRef", targetGUID=memo_id)


def _code_tree(codes: tuple[QdpxCode, ...]) -> tuple[QdpxCode, ...]:
    known = {code.code_id for code in codes}
    if len(known) != len(codes):
        raise ValueError("code GUIDs must be unique")
    for code in codes:
        if code.parent_code_id is not None and code.parent_code_id not in known:
            raise ValueError("code parent is missing")
    roots = tuple(code for code in codes if code.parent_code_id is None)
    visited: set[UUID] = set()

    def visit(code: QdpxCode, stack: set[UUID]) -> None:
        if code.code_id in stack:
            raise ValueError("code hierarchy contains a cycle")
        stack.add(code.code_id)
        visited.add(code.code_id)
        for child in codes:
            if child.parent_code_id == code.code_id:
                visit(child, stack)
        stack.remove(code.code_id)

    for root in roots:
        visit(root, set())
    if visited != known:
        raise ValueError("code hierarchy contains a cycle")
    return roots


def _write_code(parent: ET.Element, code: QdpxCode, all_codes: tuple[QdpxCode, ...]) -> None:
    node = _element(
        parent,
        "Code",
        guid=code.code_id,
        name=code.name,
        isCodable="true",
        color=code.color,
    )
    _text(node, "Description", code.description)
    _note_refs(node, code.memo_ids)
    for child in all_codes:
        if child.parent_code_id == code.code_id:
            _write_code(node, child, all_codes)


def _write_codings(parent: ET.Element, codings: tuple[QdpxCoding, ...]) -> None:
    for coding in codings:
        node = _element(
            parent,
            "Coding",
            guid=coding.coding_id,
            creatingUser=coding.user_id,
        )
        _element(node, "CodeRef", targetGUID=coding.code_id)
        _note_refs(node, coding.memo_ids)


def _variable_type(values: list[QdpxScalar]) -> str:
    concrete = [value for value in values if value is not None]
    if not concrete:
        return "Text"
    types = {type(value) for value in concrete}
    if types == {bool}:
        return "Boolean"
    if types <= {int}:
        return "Integer"
    if types <= {int, float} and bool not in types:
        return "Float"
    return "Text"


def _variable_definitions(project: QdpxProject) -> dict[str, tuple[UUID, str]]:
    names = sorted({name for case in project.cases for name in case.attributes})
    return {
        name: (
            uuid5(_VARIABLE_NAMESPACE, f"{project.name}\0{name}"),
            _variable_type([case.attributes.get(name) for case in project.cases]),
        )
        for name in names
    }


def _write_variable_value(
    parent: ET.Element,
    *,
    variable_id: UUID,
    variable_type: str,
    value: QdpxScalar,
) -> None:
    node = _element(parent, "VariableValue")
    _element(node, "VariableRef", targetGUID=variable_id)
    if value is None:
        return
    element_name = {
        "Text": "TextValue",
        "Boolean": "BooleanValue",
        "Integer": "IntegerValue",
        "Float": "FloatValue",
    }[variable_type]
    rendered = ("true" if value is True else "false") if variable_type == "Boolean" else str(value)
    _text(node, element_name, rendered)


def _project_xml(project: QdpxProject) -> tuple[bytes, tuple[ExchangeLoss, ...]]:
    losses: list[ExchangeLoss] = []
    if project.project_id is not None:
        losses.append(
            ExchangeLoss(
                object_type="project",
                object_id=str(project.project_id),
                field="project_id",
                reason="REFI-QDA Project 1.0 has no project GUID attribute",
                disposition="recovery_manifest",
                severity=ExchangeLossSeverity.INFO,
            )
        )
    root = ET.Element(
        _q("Project"),
        {
            "name": project.name,
            "origin": project.origin,
            **({"creatingUserGUID": str(project.users[0].user_id)} if project.users else {}),
        },
    )
    if project.users:
        users = _element(root, "Users")
        for user in project.users:
            _element(
                users,
                "User",
                guid=user.user_id,
                name=user.name,
                id=user.external_id,
            )
    if project.codes:
        code_book = _element(root, "CodeBook")
        codes = _element(code_book, "Codes")
        for code in _code_tree(project.codes):
            _write_code(codes, code, project.codes)

    variable_defs = _variable_definitions(project)
    if variable_defs:
        variables = _element(root, "Variables")
        for name, (variable_id, variable_type) in variable_defs.items():
            _element(
                variables,
                "Variable",
                guid=variable_id,
                name=name,
                typeOfVariable=variable_type,
            )
    if project.cases:
        cases = _element(root, "Cases")
        for case in project.cases:
            node = _element(cases, "Case", guid=case.case_id, name=case.name)
            _text(node, "Description", case.description)
            for name in sorted(case.attributes):
                variable_id, variable_type = variable_defs[name]
                value = case.attributes[name]
                if value is None:
                    losses.append(
                        ExchangeLoss(
                            object_type="case",
                            object_id=str(case.case_id),
                            field=f"attributes.{name}",
                            reason="REFI-QDA does not distinguish null from an empty value",
                            disposition="recovery_manifest",
                        )
                    )
                _write_variable_value(
                    node,
                    variable_id=variable_id,
                    variable_type=variable_type,
                    value=value,
                )
            for source_id in case.source_ids:
                _element(node, "SourceRef", targetGUID=source_id)
            for selection_id in case.selection_ids:
                _element(node, "SelectionRef", targetGUID=selection_id)

    if project.sources:
        sources = _element(root, "Sources")
        source_element = {
            QdpxSourceKind.TEXT: "TextSource",
            QdpxSourceKind.PDF: "PDFSource",
            QdpxSourceKind.PICTURE: "PictureSource",
            QdpxSourceKind.AUDIO: "AudioSource",
            QdpxSourceKind.VIDEO: "VideoSource",
        }
        for source in project.sources:
            attrs: dict[str, object] = {
                "guid": source.source_id,
                "name": source.name,
                "creatingUser": source.user_id,
                "creationDateTime": _REFI_TIMESTAMP,
            }
            if source.kind is QdpxSourceKind.TEXT:
                attrs["plainTextPath"] = f"internal://{source.source_id}.txt"
            else:
                attrs["path"] = source.path
            node = _element(sources, source_element[source.kind], **attrs)
            _text(node, "Description", source.description)
            if source.kind is QdpxSourceKind.TEXT:
                for selection in source.selections:
                    selection_node = _element(
                        node,
                        "PlainTextSelection",
                        guid=selection.selection_id,
                        name=selection.name,
                        startPosition=selection.start_position,
                        endPosition=selection.end_position,
                    )
                    _text(selection_node, "Description", selection.description)
                    _write_codings(selection_node, selection.codings)
                    _note_refs(selection_node, selection.memo_ids)
            elif source.selections:
                losses.append(
                    ExchangeLoss(
                        object_type="source",
                        object_id=str(source.source_id),
                        field="selections",
                        reason="this adapter only proves text selection coordinates",
                        disposition="recovery_manifest",
                        severity=ExchangeLossSeverity.BLOCKING,
                    )
                )
            _note_refs(node, source.memo_ids)

    if project.memos:
        notes = _element(root, "Notes")
        for memo in project.memos:
            node = _element(
                notes,
                "Note",
                guid=memo.memo_id,
                name=memo.name,
                creatingUser=memo.user_id,
                creationDateTime=_REFI_TIMESTAMP,
                plainTextPath=f"internal://{memo.memo_id}.txt",
            )
    if project.links:
        links = _element(root, "Links")
        for link in project.links:
            node = _element(
                links,
                "Link",
                guid=link.link_id,
                name=link.name,
                direction=link.direction,
                originGUID=link.origin_id,
                targetGUID=link.target_id,
            )
            _note_refs(node, link.memo_ids)
    if project.sets:
        sets = _element(root, "Sets")
        for value in project.sets:
            node = _element(sets, "Set", guid=value.set_id, name=value.name)
            _text(node, "Description", value.description)
            for code_id in value.member_code_ids:
                _element(node, "MemberCode", targetGUID=code_id)
            for source_id in value.member_source_ids:
                _element(node, "MemberSource", targetGUID=source_id)
            for memo_id in value.member_memo_ids:
                _element(node, "MemberNote", targetGUID=memo_id)
    _text(root, "Description", project.description)
    xml = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    return xml, tuple(losses)


def _zip_member(name: str, content: bytes) -> tuple[ZipInfo, bytes]:
    info = ZipInfo(name, date_time=_ZIP_TIMESTAMP)
    info.compress_type = ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    info.create_system = 3
    return info, content


def export_qdpx(project: QdpxProject) -> QdpxExport:
    project_xml, losses = _project_xml(project)
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        info, content = _zip_member("project.qde", project_xml)
        archive.writestr(info, content)
        for source in project.sources:
            if source.kind is QdpxSourceKind.TEXT:
                info, content = _zip_member(
                    f"Sources/{source.source_id}.txt",
                    (source.plain_text or "").encode("utf-8"),
                )
                archive.writestr(info, content)
        for memo in project.memos:
            info, content = _zip_member(
                f"Sources/{memo.memo_id}.txt",
                memo.content.encode("utf-8"),
            )
            archive.writestr(info, content)
    payload = output.getvalue()
    validation = validate_qdpx(payload)
    if not validation.valid:
        raise ValueError(f"QDPX schema validation failed: {'; '.join(validation.errors)}")
    return QdpxExport(
        payload=payload,
        sha256=hashlib.sha256(payload).hexdigest(),
        report=ExchangeReport(losses=losses),
    )


def _safe_members(archive: ZipFile) -> tuple[ZipInfo, ...]:
    members = tuple(archive.infolist())
    if len(members) > _MAX_ARCHIVE_MEMBERS:
        raise ValueError("QDPX archive contains too many members")
    seen: set[str] = set()
    total_size = 0
    for member in members:
        path = PurePosixPath(member.filename)
        if path.is_absolute() or ".." in path.parts or "\\" in member.filename:
            raise ValueError(f"unsafe archive member: {member.filename}")
        if member.filename in seen:
            raise ValueError(f"duplicate archive member: {member.filename}")
        seen.add(member.filename)
        total_size += member.file_size
        if total_size > _MAX_ARCHIVE_BYTES:
            raise ValueError("QDPX archive exceeds the uncompressed size limit")
    return members


def _read_qdpx(payload: bytes) -> tuple[bytes, dict[str, bytes]]:
    try:
        with ZipFile(BytesIO(payload)) as archive:
            _safe_members(archive)
            try:
                info = archive.getinfo("project.qde")
            except KeyError as error:
                raise ValueError("QDPX archive is missing project.qde") from error
            if info.file_size > _MAX_PROJECT_XML_BYTES:
                raise ValueError("project.qde exceeds the size limit")
            xml = archive.read(info)
            members = {
                member.filename: archive.read(member)
                for member in archive.infolist()
                if member.filename != "project.qde" and not member.is_dir()
            }
    except BadZipFile as error:
        raise ValueError("invalid QDPX ZIP archive") from error
    lowered = xml[:4096].lower()
    if b"<!doctype" in lowered or b"<!entity" in lowered:
        raise ValueError("QDPX XML declarations are not allowed")
    return xml, members


def _read_project_xml(payload: bytes) -> bytes:
    return _read_qdpx(payload)[0]


@lru_cache(maxsize=1)
def _schema() -> xmlschema.XMLSchema:
    path = Path(__file__).with_name("resources") / "Project.xsd"
    return xmlschema.XMLSchema(path)


def validate_qdpx(payload: bytes) -> QdpxValidation:
    try:
        xml = _read_project_xml(payload)
        errors = tuple(str(error.reason) for error in _schema().iter_errors(xml))
    except (ValueError, xmlschema.XMLSchemaException, ET.ParseError) as error:
        return QdpxValidation(valid=False, errors=(str(error),))
    return QdpxValidation(valid=not errors, errors=errors)


def _uuid(value: str | None, field: str) -> UUID:
    if value is None:
        raise ValueError(f"QDPX {field} is missing")
    try:
        return UUID(value.strip("{}"))
    except ValueError as error:
        raise ValueError(f"QDPX {field} is not a GUID") from error


def _direct_note_ids(node: ET.Element) -> tuple[UUID, ...]:
    return tuple(
        _uuid(child.get("targetGUID"), "note reference") for child in node.findall(_q("NoteRef"))
    )


def _parse_codes(container: ET.Element | None) -> tuple[QdpxCode, ...]:
    if container is None:
        return ()
    values: list[QdpxCode] = []

    def parse(node: ET.Element, parent_id: UUID | None) -> None:
        code_id = _uuid(node.get("guid"), "code GUID")
        description = node.findtext(_q("Description"))
        values.append(
            QdpxCode(
                code_id=code_id,
                name=node.get("name") or "",
                description=description,
                parent_code_id=parent_id,
                color=node.get("color"),
                memo_ids=_direct_note_ids(node),
            )
        )
        for child in node.findall(_q("Code")):
            parse(child, code_id)

    for node in container.findall(_q("Code")):
        parse(node, None)
    return tuple(values)


def _parse_codings(parent: ET.Element) -> tuple[QdpxCoding, ...]:
    values: list[QdpxCoding] = []
    for node in parent.findall(_q("Coding")):
        code_ref = node.find(_q("CodeRef"))
        if code_ref is None:
            raise ValueError("QDPX coding is missing CodeRef")
        values.append(
            QdpxCoding(
                coding_id=_uuid(node.get("guid"), "coding GUID"),
                code_id=_uuid(code_ref.get("targetGUID"), "code reference"),
                memo_ids=_direct_note_ids(node),
                user_id=(
                    _uuid(node.get("creatingUser"), "coding user")
                    if node.get("creatingUser")
                    else None
                ),
            )
        )
    return tuple(values)


def _embedded_text(node: ET.Element, members: dict[str, bytes]) -> str | None:
    inline = node.findtext(_q("PlainTextContent"))
    if inline is not None:
        return inline
    path = node.get("plainTextPath")
    if path is None:
        return None
    if not path.startswith("internal://"):
        raise ValueError("QDPX text path is not embedded")
    member_name = f"Sources/{path.removeprefix('internal://').lstrip('/')}"
    try:
        return members[member_name].decode("utf-8")
    except KeyError as error:
        raise ValueError(f"QDPX embedded text is missing: {member_name}") from error
    except UnicodeDecodeError as error:
        raise ValueError(f"QDPX embedded text is not UTF-8: {member_name}") from error


def _parse_sources(
    container: ET.Element | None,
    members: dict[str, bytes],
) -> tuple[QdpxSource, ...]:
    if container is None:
        return ()
    kinds = {
        _q("TextSource"): QdpxSourceKind.TEXT,
        _q("PDFSource"): QdpxSourceKind.PDF,
        _q("PictureSource"): QdpxSourceKind.PICTURE,
        _q("AudioSource"): QdpxSourceKind.AUDIO,
        _q("VideoSource"): QdpxSourceKind.VIDEO,
    }
    values: list[QdpxSource] = []
    for node in container:
        kind = kinds[node.tag]
        selections = tuple(
            QdpxSelection(
                selection_id=_uuid(selection.get("guid"), "selection GUID"),
                name=selection.get("name"),
                description=selection.findtext(_q("Description")),
                start_position=int(selection.get("startPosition") or "0"),
                end_position=int(selection.get("endPosition") or "0"),
                codings=_parse_codings(selection),
                memo_ids=_direct_note_ids(selection),
            )
            for selection in node.findall(_q("PlainTextSelection"))
        )
        values.append(
            QdpxSource(
                source_id=_uuid(node.get("guid"), "source GUID"),
                name=node.get("name") or "",
                kind=kind,
                plain_text=_embedded_text(node, members),
                path=node.get("path"),
                description=node.findtext(_q("Description")),
                selections=selections,
                memo_ids=_direct_note_ids(node),
                user_id=(
                    _uuid(node.get("creatingUser"), "source user")
                    if node.get("creatingUser")
                    else None
                ),
            )
        )
    return tuple(values)


def _parse_variables(container: ET.Element | None) -> dict[UUID, tuple[str, str]]:
    if container is None:
        return {}
    return {
        _uuid(node.get("guid"), "variable GUID"): (
            node.get("name") or "",
            node.get("typeOfVariable") or "Text",
        )
        for node in container.findall(_q("Variable"))
    }


def _parse_scalar(node: ET.Element, variable_type: str) -> QdpxScalar:
    value_nodes = [child for child in node if child.tag != _q("VariableRef")]
    if not value_nodes:
        return None
    raw = value_nodes[0].text or ""
    if variable_type == "Boolean":
        return raw.lower() in {"true", "1"}
    if variable_type == "Integer":
        return int(raw)
    if variable_type == "Float":
        return float(raw)
    return raw


def _parse_cases(
    container: ET.Element | None,
    variables: dict[UUID, tuple[str, str]],
) -> tuple[QdpxCase, ...]:
    if container is None:
        return ()
    values: list[QdpxCase] = []
    for node in container.findall(_q("Case")):
        attributes: dict[str, QdpxScalar] = {}
        for variable_value in node.findall(_q("VariableValue")):
            variable_ref = variable_value.find(_q("VariableRef"))
            if variable_ref is None:
                raise ValueError("QDPX variable value is missing VariableRef")
            variable_id = _uuid(variable_ref.get("targetGUID"), "variable reference")
            try:
                name, variable_type = variables[variable_id]
            except KeyError as error:
                raise ValueError("QDPX variable reference is unresolved") from error
            attributes[name] = _parse_scalar(variable_value, variable_type)
        values.append(
            QdpxCase(
                case_id=_uuid(node.get("guid"), "case GUID"),
                name=node.get("name") or "",
                description=node.findtext(_q("Description")),
                attributes=attributes,
                source_ids=tuple(
                    _uuid(ref.get("targetGUID"), "source reference")
                    for ref in node.findall(_q("SourceRef"))
                ),
                selection_ids=tuple(
                    _uuid(ref.get("targetGUID"), "selection reference")
                    for ref in node.findall(_q("SelectionRef"))
                ),
            )
        )
    return tuple(values)


def _memo_targets(root: ET.Element) -> dict[UUID, list[UUID]]:
    targets: dict[UUID, list[UUID]] = {}
    for node in root.iter():
        guid = node.get("guid")
        if guid is None or node.tag == _q("Note"):
            continue
        target_id = _uuid(guid, "target GUID")
        for note_ref in node.findall(_q("NoteRef")):
            memo_id = _uuid(note_ref.get("targetGUID"), "note reference")
            targets.setdefault(memo_id, []).append(target_id)
    return targets


def _parse_project(xml: bytes, members: dict[str, bytes]) -> QdpxProject:
    root = ET.fromstring(xml)
    users_node = root.find(_q("Users"))
    users = tuple(
        QdpxUser(
            user_id=_uuid(node.get("guid"), "user GUID"),
            name=node.get("name") or "",
            external_id=node.get("id"),
        )
        for node in (() if users_node is None else users_node.findall(_q("User")))
    )
    code_book = root.find(_q("CodeBook"))
    codes = _parse_codes(None if code_book is None else code_book.find(_q("Codes")))
    variables = _parse_variables(root.find(_q("Variables")))
    sources = _parse_sources(root.find(_q("Sources")), members)
    targets = _memo_targets(root)
    notes_node = root.find(_q("Notes"))
    memos = tuple(
        QdpxMemo(
            memo_id=(memo_id := _uuid(node.get("guid"), "memo GUID")),
            name=node.get("name") or "",
            content=_embedded_text(node, members) or "",
            target_ids=tuple(targets.get(memo_id, ())),
            user_id=(
                _uuid(node.get("creatingUser"), "memo user") if node.get("creatingUser") else None
            ),
        )
        for node in (() if notes_node is None else notes_node.findall(_q("Note")))
    )
    links_node = root.find(_q("Links"))
    links = tuple(
        QdpxLink(
            link_id=_uuid(node.get("guid"), "link GUID"),
            name=node.get("name") or "",
            origin_id=_uuid(node.get("originGUID"), "link origin"),
            target_id=_uuid(node.get("targetGUID"), "link target"),
            direction=node.get("direction") or "Associative",
            memo_ids=_direct_note_ids(node),
        )
        for node in (() if links_node is None else links_node.findall(_q("Link")))
    )
    sets_node = root.find(_q("Sets"))
    sets = tuple(
        QdpxSet(
            set_id=_uuid(node.get("guid"), "set GUID"),
            name=node.get("name") or "",
            description=node.findtext(_q("Description")),
            member_code_ids=tuple(
                _uuid(ref.get("targetGUID"), "set code reference")
                for ref in node.findall(_q("MemberCode"))
            ),
            member_source_ids=tuple(
                _uuid(ref.get("targetGUID"), "set source reference")
                for ref in node.findall(_q("MemberSource"))
            ),
            member_memo_ids=tuple(
                _uuid(ref.get("targetGUID"), "set memo reference")
                for ref in node.findall(_q("MemberNote"))
            ),
        )
        for node in (() if sets_node is None else sets_node.findall(_q("Set")))
    )
    return QdpxProject(
        project_id=None,
        name=root.get("name") or "",
        origin=root.get("origin") or "unknown",
        description=root.findtext(_q("Description")),
        users=users,
        codes=codes,
        sources=sources,
        memos=memos,
        cases=_parse_cases(root.find(_q("Cases")), variables),
        sets=sets,
        links=links,
    )


def import_qdpx(payload: bytes) -> QdpxImport:
    xml, members = _read_qdpx(payload)
    validation = validate_qdpx(payload)
    if not validation.valid:
        raise ValueError(f"QDPX schema validation failed: {'; '.join(validation.errors)}")
    return QdpxImport(project=_parse_project(xml, members), report=ExchangeReport())
