"""Deterministic, no-OCR parsers for the first personal-material slice.

The output is a sequence of source blocks, rather than one flattened string.
Every block carries a locator so retrieval and citation can point back to the
same source unit.  PDF extraction intentionally uses embedded text only;
there is no image/OCR fallback in this adapter.
"""

from __future__ import annotations

import hashlib
import re
from array import array
from collections.abc import Iterator
from dataclasses import dataclass, field
from io import BytesIO
from itertools import pairwise
from typing import Any
from uuid import UUID, uuid4
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile, ZipInfo

from markdown_it import MarkdownIt
from pypdf import PageObject, PdfReader

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
_MAX_ZIP_MEMBERS = 10_000
_MAX_ZIP_MEMBER_BYTES = 16 * 1024 * 1024
_MAX_ZIP_EXPANDED_BYTES = 64 * 1024 * 1024
_MAX_DOCUMENT_PAGES = 1_000
_MAX_DOCUMENT_BLOCKS = 10_000
_MAX_DOCUMENT_TEXT_CHARS = 8 * 1024 * 1024
_LINE_BREAK = re.compile(r"\r\n|[\n\r\v\f\x1c-\x1e\x85\u2028\u2029]")


def _check_page_budget(page_count: int) -> None:
    if page_count > _MAX_DOCUMENT_PAGES:
        raise MaterialParseError("document_too_large", "文档页数超过可处理上限。")


def _check_text_budget(char_count: int) -> None:
    if char_count > _MAX_DOCUMENT_TEXT_CHARS:
        raise MaterialParseError("document_too_large", "文档文本超过可处理长度。")


@dataclass(slots=True)
class _MaterialBlocks:
    material_id: UUID
    parse_id: UUID
    items: list[MaterialBlock] = field(default_factory=list)
    text_chars: int = 0

    def add(self, *, kind: str, text: str, locator: MaterialLocator) -> None:
        ordinal = len(self.items)
        if ordinal >= _MAX_DOCUMENT_BLOCKS:
            raise MaterialParseError("document_too_large", "文档片段数超过可处理上限。")
        # full_text joins blocks with a blank line.
        self.text_chars += len(text) + (2 if ordinal else 0)
        _check_text_budget(self.text_chars)
        self.items.append(
            MaterialBlock.create(
                material_id=self.material_id,
                parse_id=self.parse_id,
                ordinal=ordinal,
                kind=kind,
                text=text,
                locator=locator,
            )
        )

    def full_text(self) -> str:
        return "\n\n".join(block.text for block in self.items)


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
    blocks = _MaterialBlocks(material_id or UUID(int=0), parse_id or uuid4())
    if material_format is MaterialFormat.TXT:
        full_text, structure = _parse_text(content, blocks)
    elif material_format is MaterialFormat.MARKDOWN:
        full_text, structure = _parse_markdown(content, blocks)
    elif material_format is MaterialFormat.DOCX:
        full_text, structure = _parse_docx(content, blocks)
    elif material_format is MaterialFormat.PPTX:
        full_text, structure = _parse_pptx(content, blocks)
    elif material_format is MaterialFormat.PDF:
        full_text, structure = _parse_pdf(content, blocks)
    else:  # pragma: no cover - exhaustive enum guard
        raise MaterialParseError("unsupported_format")
    if not full_text.strip() or not blocks.items:
        raise MaterialParseError("no_extractable_text", "文件中没有可直接提取的文字。")
    return ParsedMaterial(
        full_text=full_text,
        structured_document=structure,
        blocks=tuple(blocks.items),
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
    blocks: _MaterialBlocks,
) -> tuple[str, dict[str, Any]]:
    text = _decode_utf8(content).strip("\n")
    _check_text_budget(len(text))
    _add_line_paragraphs(text, blocks)
    return text, {"format": "txt", "line_count": text.count("\n") + 1}


def _parse_markdown(
    content: bytes,
    blocks: _MaterialBlocks,
) -> tuple[str, dict[str, Any]]:
    text = _decode_utf8(content).strip("\n")
    _check_text_budget(len(text))
    parser = MarkdownIt("commonmark", {"html": False})
    tokens = parser.parse(text)
    offsets = array("I", _line_offsets(text))
    headings: list[str] = []
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
            blocks.add(
                kind=kind,
                text=value,
                locator=MaterialLocator(
                    section_path=path,
                    line_start=start_line,
                    line_end=end_line,
                    char_start=offsets[start_line - 1],
                    char_end=offsets[end_line],
                ),
            )
            index += 2
            continue
        value = token.content.strip()
        if value:
            line_map = token.map or [0, 1]
            start_line, end_line = int(line_map[0]) + 1, int(line_map[1])
            blocks.add(
                kind="code",
                text=value,
                locator=MaterialLocator(
                    section_path=tuple(headings),
                    line_start=start_line,
                    line_end=end_line,
                    char_start=offsets[start_line - 1],
                    char_end=offsets[end_line],
                ),
            )
        index += 1
    if not blocks.items:
        _add_line_paragraphs(text, blocks)
    return blocks.full_text(), {"format": "markdown", "block_count": len(blocks.items)}


def _check_zip_member_count(archive: ZipFile, message: str) -> None:
    if len(archive.infolist()) > _MAX_ZIP_MEMBERS:
        raise MaterialParseError("document_too_large", message)


def _check_zip_expansion(members: list[ZipInfo], message: str) -> None:
    if any(member.file_size > _MAX_ZIP_MEMBER_BYTES for member in members):
        raise MaterialParseError("document_too_large", message)
    if sum(member.file_size for member in members) > _MAX_ZIP_EXPANDED_BYTES:
        raise MaterialParseError("document_too_large", message)


def _read_zip_member(archive: ZipFile, info: ZipInfo) -> bytes:
    with archive.open(info) as member:
        return member.read(info.file_size + 1)


def _parse_docx(content: bytes, blocks: _MaterialBlocks) -> tuple[str, dict[str, Any]]:
    namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    size_error = "文档正文超过可处理大小。"
    try:
        with ZipFile(BytesIO(content)) as archive:
            _check_zip_member_count(archive, size_error)
            document_info = archive.getinfo("word/document.xml")
            styles_info = (
                archive.getinfo("word/styles.xml")
                if "word/styles.xml" in archive.namelist()
                else None
            )
            members = [document_info, styles_info] if styles_info is not None else [document_info]
            _check_zip_expansion(members, size_error)
            document_xml = _read_zip_member(archive, document_info)
            styles_xml = _read_zip_member(archive, styles_info) if styles_info is not None else b""
        root = ElementTree.fromstring(document_xml)
        styles = ElementTree.fromstring(styles_xml) if styles_xml else None
    except (BadZipFile, KeyError, ElementTree.ParseError) as error:
        raise MaterialParseError("invalid_docx", "DOCX 文件损坏或无法读取。") from error

    heading_styles = _docx_heading_styles(styles, namespace)
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
            blocks.add(
                kind=kind,
                text=value,
                locator=MaterialLocator(
                    section_path=tuple(headings),
                    paragraph=paragraph_number,
                ),
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
                blocks.add(
                    kind="table",
                    text=value,
                    locator=MaterialLocator(
                        section_path=tuple(headings),
                        paragraph=paragraph_number or None,
                    ),
                )
    structure = {
        "format": "docx",
        "block_count": len(blocks.items),
        "paragraph_count": paragraph_number,
    }
    return blocks.full_text(), structure


class _BoundedPdfPages(list[PageObject]):
    def append(self, page: PageObject) -> None:
        _check_page_budget(len(self) + 1)
        super().append(page)


class _BoundedPdfReader(PdfReader):
    def _flatten(self, *args: Any, **kwargs: Any) -> None:
        # pypdf 6 builds its page list while resolving inheritance. Bound that list
        # during traversal, since len(reader.pages) flattens the tree first.
        if type(self.flattened_pages) is list:
            self.flattened_pages = _BoundedPdfPages(self.flattened_pages)
        super()._flatten(*args, **kwargs)


def _parse_pdf(content: bytes, blocks: _MaterialBlocks) -> tuple[str, dict[str, Any]]:
    try:
        reader = _BoundedPdfReader(BytesIO(content), strict=False)
        page_count = len(reader.pages)
        _check_page_budget(page_count)
    except MaterialParseError:
        raise
    except Exception as error:  # pypdf exposes several parser-specific errors
        # A malformed or image-only PDF has no usable text for this phase.  We
        # deliberately use the same public code as the no-text outcome so the
        # caller never infers that an OCR fallback exists.
        raise MaterialParseError("no_extractable_text", "PDF 文件损坏或无法读取。") from error
    extracted_chars = 0
    pages: list[dict[str, Any]] = []
    for page_number, page in enumerate(reader.pages, start=1):
        try:
            try:
                extracted = page.extract_text(extraction_mode="layout") or ""
            except TypeError:
                extracted = page.extract_text() or ""
        except Exception as error:
            raise MaterialParseError("pdf_text_extraction_failed", "PDF 正文提取失败。") from error
        extracted_chars += len(extracted)
        _check_text_budget(extracted_chars)
        normalized = extracted.replace("\r\n", "\n").replace("\r", "\n").strip()
        pages.append({"page": page_number, "text": normalized})
        if normalized:
            _add_line_paragraphs(normalized, blocks, page=page_number)
    full_text = blocks.full_text()
    if not full_text.strip():
        raise MaterialParseError(
            "no_extractable_text",
            "PDF 中没有可直接提取的文字；图片或扫描件 OCR 暂不支持。",
        )
    return full_text, {"format": "pdf", "page_count": page_count, "pages": pages}


def _add_line_paragraphs(
    text: str,
    blocks: _MaterialBlocks,
    *,
    page: int | None = None,
) -> None:
    paragraph_number = 0
    line_start = line_end = char_start = char_end = 0
    paragraph_lines: list[str] = []

    def flush() -> None:
        nonlocal paragraph_number
        if not paragraph_lines:
            return
        paragraph_number += 1
        blocks.add(
            kind="paragraph",
            text="\n".join(paragraph_lines).strip(),
            locator=MaterialLocator(
                page=page,
                paragraph=paragraph_number,
                line_start=line_start,
                line_end=line_end,
                char_start=char_start,
                char_end=char_end,
            ),
        )
        paragraph_lines.clear()

    for line_number, (start, end) in enumerate(pairwise(_line_offsets(text)), start=1):
        line = text[start:end].rstrip()
        if not line:
            flush()
            continue
        if not paragraph_lines:
            line_start, char_start = line_number, start
        line_end, char_end = line_number, end
        paragraph_lines.append(line)
    flush()


def _line_offsets(text: str) -> Iterator[int]:
    # Match splitlines() boundaries without splitting the whole text for every locator.
    yield 0
    end = 0
    for match in _LINE_BREAK.finditer(text):
        end = match.end()
        yield end
    if end < len(text):
        yield len(text)


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


def _parse_pptx(content: bytes, blocks: _MaterialBlocks) -> tuple[str, dict[str, Any]]:
    """Only visible slide text and tables are shared; notes and hidden slides are excluded."""
    import posixpath

    p = "{http://schemas.openxmlformats.org/presentationml/2006/main}"
    a = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
    r = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
    skipped: list[int] = []
    size_error = "课件解压后的内容过大。"
    try:
        with ZipFile(BytesIO(content)) as archive:
            _check_zip_member_count(archive, size_error)
            metadata = [
                archive.getinfo("ppt/presentation.xml"),
                archive.getinfo("ppt/_rels/presentation.xml.rels"),
            ]
            _check_zip_expansion(metadata, size_error)

            def read_xml(info: ZipInfo) -> ElementTree.Element:
                raw = _read_zip_member(archive, info)
                upper = raw.upper()
                if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
                    raise MaterialParseError("invalid_pptx", "课件包含不支持的 XML 声明。")
                return ElementTree.fromstring(raw)

            presentation, relationships = (read_xml(info) for info in metadata)
            targets = {item.get("Id"): item.get("Target", "") for item in relationships
                       if item.get("TargetMode") != "External"}
            slide_refs = presentation.findall(f"{p}sldIdLst/{p}sldId")
            _check_page_budget(len(slide_refs))
            slides: list[ZipInfo] = []
            for slide_ref in slide_refs:
                target = targets.get(slide_ref.get(f"{r}id"), "")
                name = posixpath.normpath(
                    target.lstrip("/") if target.startswith("/") else "ppt/" + target
                )
                if not name.startswith("ppt/slides/") or not name.endswith(".xml"):
                    raise MaterialParseError("invalid_pptx", "课件幻灯片引用无效。")
                slides.append(archive.getinfo(name))
            _check_zip_expansion([*metadata, *slides], size_error)

            for page, info in enumerate(slides, start=1):
                slide = read_xml(info)
                if slide.get("show") in {"0", "false"}:
                    continue
                # Remove hidden containers before extracting descendants, including grouped tables.
                def remove_hidden(parent):
                    for child in list(parent):
                        hidden = any(
                            props.get("hidden") in {"1", "true"}
                            for wrapper in child
                            if wrapper.tag in {
                                f"{p}nvSpPr", f"{p}nvGrpSpPr", f"{p}nvGraphicFramePr"
                            }
                            for props in wrapper.findall(f"{p}cNvPr")
                        )
                        if hidden:
                            parent.remove(child)
                        else:
                            remove_hidden(child)

                remove_hidden(slide)
                title, lines = "", []
                for shape in slide.findall(f".//{p}sp"):
                    props = shape.find(f"{p}nvSpPr/{p}cNvPr")
                    if props is not None and props.get("hidden") in {"1", "true"}:
                        continue
                    paragraphs = ["".join(node.text or "" for node in para.iter(f"{a}t"))
                                  for para in shape.findall(f"{p}txBody/{a}p")]
                    text = "\n".join(value for value in paragraphs if value.strip())
                    placeholder = shape.find(f"{p}nvSpPr/{p}nvPr/{p}ph")
                    if placeholder is not None and placeholder.get("type") in {"title", "ctrTitle"}:
                        title = text
                    if text:
                        lines.append(text)
                for table in slide.findall(f".//{a}tbl"):
                    for row in table.findall(f"{a}tr"):
                        cells = [" ".join(node.text or "" for node in cell.iter(f"{a}t"))
                                 for cell in row.findall(f"{a}tc")]
                        lines.append(" | ".join(cells))
                text = "\n\n".join(lines).strip()
                if not text:
                    skipped.append(page)
                    continue
                # Short slides stay intact; long pages split without losing slide identity.
                for start in range(0, len(text), 4000):
                    blocks.add(
                        kind="paragraph",
                        text=text[start : start + 4000],
                        locator=MaterialLocator(
                            page=page,
                            section_path=(title or f"第 {page} 张幻灯片",),
                            char_start=start,
                            char_end=min(start + 4000, len(text)),
                        ),
                    )
    except (BadZipFile, KeyError, ElementTree.ParseError, RuntimeError) as error:
        raise MaterialParseError("invalid_pptx", "课件损坏或已加密，无法提取文字。") from error
    return blocks.full_text(), {
        "format": "pptx", "unreadable_slides": skipped,
    }
