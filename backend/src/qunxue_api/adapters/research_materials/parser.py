"""Deterministic, no-OCR parsers for the first personal-material slice.

The output is a sequence of source blocks, rather than one flattened string.
Every block carries a locator so retrieval and citation can point back to the
same source unit.  PDF extraction intentionally uses embedded text only;
there is no image/OCR fallback in this adapter.
"""

from __future__ import annotations

import hashlib
import re
from io import BytesIO
from typing import Any
from uuid import UUID, uuid4
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

from markdown_it import MarkdownIt
from pypdf import PdfReader

from qunxue_api.modules.research_materials import (
    MaterialBlock,
    MaterialFormat,
    MaterialLocator,
    MaterialParseError,
    ParsedMaterial,
    UnsupportedMaterialFormat,
)

_PARSER_NAME = "qunxue-deterministic-document-parser"
_PARSER_VERSION = "1.0"
_SCHEMA_VERSION = "1"
_MAX_ZIP_MEMBER_BYTES = 16 * 1024 * 1024
def parse_material(
    *,
    filename: str,
    media_type: str | None,
    content: bytes,
    material_id: UUID | None = None,
    parse_id: UUID | None = None,
) -> ParsedMaterial:
    """Parse one supported document while keeping source-level locators.

    ``material_id`` and ``parse_id`` are optional for pure parser tests.  The
    application supplies them so block IDs remain tied to a specific parse
    version and cannot be confused with a different material.
    """

    material_format = _format_for(filename=filename, media_type=media_type)
    if not content:
        raise MaterialParseError("empty_material", "材料为空，无法解析。")
    resolved_material_id = material_id or UUID(int=0)
    resolved_parse_id = parse_id or uuid4()
    if material_format is MaterialFormat.TXT:
        blocks, full_text, structure = _parse_text(
            content,
            material_id=resolved_material_id,
            parse_id=resolved_parse_id,
        )
    elif material_format is MaterialFormat.MARKDOWN:
        blocks, full_text, structure = _parse_markdown(
            content,
            material_id=resolved_material_id,
            parse_id=resolved_parse_id,
        )
    elif material_format is MaterialFormat.DOCX:
        blocks, full_text, structure = _parse_docx(
            content,
            material_id=resolved_material_id,
            parse_id=resolved_parse_id,
        )
    elif material_format is MaterialFormat.PDF:
        blocks, full_text, structure = _parse_pdf(
            content,
            material_id=resolved_material_id,
            parse_id=resolved_parse_id,
        )
    else:  # pragma: no cover - exhaustive enum guard
        raise MaterialParseError("unsupported_format")
    if not full_text.strip() or not blocks:
        raise MaterialParseError("no_extractable_text", "文件中没有可直接提取的文字。")
    return ParsedMaterial(
        full_text=full_text,
        structured_document=structure,
        blocks=blocks,
        content_hash=hashlib.sha256(content).hexdigest(),
        parser_name=_PARSER_NAME,
        parser_version=_PARSER_VERSION,
        schema_version=_SCHEMA_VERSION,
    )


def _format_for(*, filename: str, media_type: str | None) -> MaterialFormat:
    """Resolve format through the public domain contract.

    The upload transport is allowed to omit a MIME or send the generic
    octet-stream value.  The filename is authoritative in those cases.  We
    retain parser-specific error codes so the API layer can map them to its
    stable public error vocabulary.
    """

    try:
        return MaterialFormat.resolve(filename=filename, media_type=media_type)
    except UnsupportedMaterialFormat as error:
        normalized_media = (media_type or "").split(";", 1)[0].strip().lower()
        try:
            MaterialFormat.from_filename(filename)
        except UnsupportedMaterialFormat:
            raise MaterialParseError("unsupported_format", "暂不支持这种材料格式。") from error
        if normalized_media in {"", "application/octet-stream"}:
            # ``resolve`` should accept generic values for every supported
            # extension; keep this guard for a future resolver regression.
            raise MaterialParseError("unsupported_format", "暂不支持这种材料格式。") from error
        try:
            MaterialFormat.from_media_type(normalized_media)
        except UnsupportedMaterialFormat:
            raise MaterialParseError("unsupported_format", "暂不支持这种材料格式。") from error
        raise MaterialParseError(
            "format_mismatch", "文件扩展名与材料格式不一致。"
        ) from error


def _decode_utf8(content: bytes) -> str:
    try:
        return content.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    except UnicodeDecodeError as error:
        raise MaterialParseError("invalid_encoding", "文件不是有效的 UTF-8 文本。") from error


def _parse_text(
    content: bytes,
    *,
    material_id: UUID,
    parse_id: UUID,
) -> tuple[tuple[MaterialBlock, ...], str, dict[str, Any]]:
    text = _decode_utf8(content).strip("\n")
    blocks = _line_paragraph_blocks(
        text,
        material_id=material_id,
        parse_id=parse_id,
        section_path=(),
    )
    return blocks, text, {"format": "txt", "line_count": text.count("\n") + 1}


def _parse_markdown(
    content: bytes,
    *,
    material_id: UUID,
    parse_id: UUID,
) -> tuple[tuple[MaterialBlock, ...], str, dict[str, Any]]:
    text = _decode_utf8(content).strip("\n")
    parser = MarkdownIt("commonmark", {"html": False})
    tokens = parser.parse(text)
    blocks: list[MaterialBlock] = []
    headings: list[str] = []
    ordinal = 0
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token.type not in {"heading_open", "paragraph_open", "fence", "code_block"}:
            index += 1
            continue
        if token.type in {"heading_open", "paragraph_open"}:
            inline = tokens[index + 1] if index + 1 < len(tokens) else None
            value = inline.content.strip() if inline and inline.type == "inline" else ""
            if not value:
                index += 1
                continue
            line_map = token.map or [0, 1]
            start_line, end_line = int(line_map[0]) + 1, int(line_map[1])
            if token.type == "heading_open":
                level = int(token.tag.removeprefix("h") or "1")
                headings = headings[: max(0, level - 1)]
                headings.append(value)
                kind = "heading"
                path = tuple(headings)
            else:
                kind = "paragraph"
                path = tuple(headings)
            ordinal += 1
            blocks.append(
                _block(
                    material_id=material_id,
                    parse_id=parse_id,
                    ordinal=ordinal - 1,
                    kind=kind,
                    text=value,
                    locator=MaterialLocator(
                        section_path=path,
                        line_start=start_line,
                        line_end=end_line,
                        char_start=_line_offset(text, start_line),
                        char_end=_line_offset(text, end_line + 1),
                    ),
                )
            )
            index += 2
            continue
        value = token.content.strip()
        if value:
            line_map = token.map or [0, 1]
            start_line, end_line = int(line_map[0]) + 1, int(line_map[1])
            ordinal += 1
            blocks.append(
                _block(
                    material_id=material_id,
                    parse_id=parse_id,
                    ordinal=ordinal - 1,
                    kind="code",
                    text=value,
                    locator=MaterialLocator(
                        section_path=tuple(headings),
                        line_start=start_line,
                        line_end=end_line,
                        char_start=_line_offset(text, start_line),
                        char_end=_line_offset(text, end_line + 1),
                    ),
                )
            )
        index += 1
    if not blocks:
        blocks = list(
            _line_paragraph_blocks(
                text,
                material_id=material_id,
                parse_id=parse_id,
                section_path=(),
            )
        )
    full_text = "\n\n".join(item.text for item in blocks)
    return tuple(blocks), full_text, {"format": "markdown", "block_count": len(blocks)}


def _parse_docx(
    content: bytes,
    *,
    material_id: UUID,
    parse_id: UUID,
) -> tuple[tuple[MaterialBlock, ...], str, dict[str, Any]]:
    namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    try:
        with ZipFile(BytesIO(content)) as archive:
            document_info = archive.getinfo("word/document.xml")
            if document_info.file_size > _MAX_ZIP_MEMBER_BYTES:
                raise MaterialParseError("document_too_large", "文档正文超过可处理大小。")
            document_xml = archive.read(document_info)
            styles_xml = (
                archive.read("word/styles.xml")
                if "word/styles.xml" in archive.namelist()
                else b""
            )
        root = ElementTree.fromstring(document_xml)
        styles = ElementTree.fromstring(styles_xml) if styles_xml else None
    except MaterialParseError:
        raise
    except (BadZipFile, KeyError, ElementTree.ParseError) as error:
        raise MaterialParseError("invalid_docx", "DOCX 文件损坏或无法读取。") from error

    heading_styles = _docx_heading_styles(styles, namespace)
    blocks: list[MaterialBlock] = []
    headings: list[str] = []
    paragraph_number = 0
    body = root.find(f"{namespace}body")
    for child in body if body is not None else ():
        if child.tag == f"{namespace}p":
            value = _docx_paragraph_text(child, namespace).strip()
            if not value:
                continue
            paragraph_number += 1
            style = _docx_paragraph_style(child, namespace)
            if style in heading_styles:
                level = heading_styles[style]
                headings = headings[: max(0, level - 1)]
                headings.append(value)
                kind = "heading"
            else:
                kind = "paragraph"
            blocks.append(
                _block(
                    material_id=material_id,
                    parse_id=parse_id,
                    ordinal=len(blocks),
                    kind=kind,
                    text=value,
                    locator=MaterialLocator(
                        section_path=tuple(headings),
                        paragraph=paragraph_number,
                    ),
                )
            )
            continue
        if child.tag == f"{namespace}tbl":
            rows: list[str] = []
            for row in child.findall(f"{namespace}tr"):
                cells = []
                for cell in row.findall(f"{namespace}tc"):
                    cells.append(" ".join(
                        part for part in (
                            _docx_paragraph_text(paragraph, namespace).strip()
                            for paragraph in cell.findall(f"{namespace}p")
                        ) if part
                    ))
                if any(cells):
                    rows.append(" | ".join(cells))
            value = "\n".join(rows).strip()
            if value:
                blocks.append(
                    _block(
                        material_id=material_id,
                        parse_id=parse_id,
                        ordinal=len(blocks),
                        kind="table",
                        text=value,
                        locator=MaterialLocator(
                            section_path=tuple(headings),
                            paragraph=paragraph_number or None,
                        ),
                    )
                )
    full_text = "\n\n".join(item.text for item in blocks)
    structure = {
        "format": "docx",
        "block_count": len(blocks),
        "paragraph_count": paragraph_number,
    }
    return tuple(blocks), full_text, structure


def _parse_pdf(
    content: bytes,
    *,
    material_id: UUID,
    parse_id: UUID,
) -> tuple[tuple[MaterialBlock, ...], str, dict[str, Any]]:
    try:
        reader = PdfReader(BytesIO(content), strict=False)
        page_count = len(reader.pages)
    except Exception as error:  # pypdf exposes several parser-specific errors
        # A malformed or image-only PDF has no usable text for this phase.  We
        # deliberately use the same public code as the no-text outcome so the
        # caller never infers that an OCR fallback exists.
        raise MaterialParseError("no_extractable_text", "PDF 文件损坏或无法读取。") from error
    blocks: list[MaterialBlock] = []
    pages: list[dict[str, Any]] = []
    for page_number, page in enumerate(reader.pages, start=1):
        try:
            try:
                extracted = page.extract_text(extraction_mode="layout") or ""
            except TypeError:
                extracted = page.extract_text() or ""
        except Exception as error:
            raise MaterialParseError("pdf_text_extraction_failed", "PDF 正文提取失败。") from error
        normalized = extracted.replace("\r\n", "\n").replace("\r", "\n").strip()
        pages.append({"page": page_number, "text": normalized})
        if not normalized:
            continue
        page_blocks = _line_paragraph_blocks(
            normalized,
            material_id=material_id,
            parse_id=parse_id,
            section_path=(),
            page=page_number,
            ordinal_offset=len(blocks),
        )
        blocks.extend(page_blocks)
    full_text = "\n\n".join(item.text for item in blocks)
    if not full_text.strip():
        raise MaterialParseError(
            "no_extractable_text",
            "PDF 中没有可直接提取的文字；图片或扫描件 OCR 暂不支持。",
        )
    return tuple(blocks), full_text, {"format": "pdf", "page_count": page_count, "pages": pages}


def _line_paragraph_blocks(
    text: str,
    *,
    material_id: UUID,
    parse_id: UUID,
    section_path: tuple[str, ...],
    page: int | None = None,
    ordinal_offset: int = 0,
) -> tuple[MaterialBlock, ...]:
    blocks: list[MaterialBlock] = []
    lines = text.splitlines()
    paragraph_start: int | None = None
    paragraph_lines: list[str] = []

    def flush(end_line: int) -> None:
        nonlocal paragraph_start, paragraph_lines
        if paragraph_start is None or not paragraph_lines:
            paragraph_start = None
            paragraph_lines = []
            return
        value = "\n".join(paragraph_lines).strip()
        if value:
            blocks.append(
                _block(
                    material_id=material_id,
                    parse_id=parse_id,
                    ordinal=ordinal_offset + len(blocks),
                    kind="paragraph",
                    text=value,
                    locator=MaterialLocator(
                        page=page,
                        section_path=section_path,
                        paragraph=len(blocks) + 1,
                        line_start=paragraph_start,
                        line_end=end_line,
                        char_start=_line_offset(text, paragraph_start),
                        char_end=_line_offset(text, end_line + 1),
                    ),
                )
            )
        paragraph_start = None
        paragraph_lines = []

    for line_number, line in enumerate(lines, start=1):
        if line.strip():
            if paragraph_start is None:
                paragraph_start = line_number
            paragraph_lines.append(line.rstrip())
        elif paragraph_start is not None:
            flush(line_number - 1)
    flush(len(lines))
    return tuple(blocks)


def _line_offset(text: str, one_based_line: int) -> int:
    if one_based_line <= 1:
        return 0
    lines = text.splitlines(keepends=True)
    return sum(len(line) for line in lines[: one_based_line - 1])


def _block(
    *,
    material_id: UUID,
    parse_id: UUID,
    ordinal: int,
    kind: str,
    text: str,
    locator: MaterialLocator,
) -> MaterialBlock:
    return MaterialBlock.create(
        parse_id=parse_id,
        material_id=material_id,
        ordinal=ordinal,
        kind=kind,
        text=text,
        locator=locator,
    )


def _docx_paragraph_text(paragraph: ElementTree.Element, namespace: str) -> str:
    values: list[str] = []
    for node in paragraph.iter():
        if node.tag == f"{namespace}t":
            values.append(node.text or "")
        elif node.tag == f"{namespace}tab":
            values.append("\t")
        elif node.tag in {f"{namespace}br", f"{namespace}cr"}:
            values.append("\n")
    return "".join(values)


def _docx_paragraph_style(paragraph: ElementTree.Element, namespace: str) -> str | None:
    properties = paragraph.find(f"{namespace}pPr")
    style = properties.find(f"{namespace}pStyle") if properties is not None else None
    return style.get(f"{namespace}val") if style is not None else None


def _docx_heading_styles(styles: ElementTree.Element | None, namespace: str) -> dict[str, int]:
    if styles is None:
        return {f"Heading{level}": level for level in range(1, 7)}
    result: dict[str, int] = {}
    for style in styles.findall(f"{namespace}style"):
        style_id = style.get(f"{namespace}styleId")
        name = style.find(f"{namespace}name")
        value = name.get(f"{namespace}val", "") if name is not None else ""
        match = re.search(r"heading\s*([1-9])", f"{style_id or ''} {value}", re.IGNORECASE)
        if style_id and match:
            result[style_id] = int(match.group(1))
    result.update(
        {
            f"Heading{level}": level
            for level in range(1, 7)
            if f"Heading{level}" not in result
        }
    )
    return result
