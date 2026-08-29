from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from qunxue_api.adapters.research_materials.parser import (
    MaterialParseError,
    parse_material,
)


def _docx_bytes() -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr(
            "word/document.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
            <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
              <w:body>
                <w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>访谈主题</w:t></w:r></w:p>
                <w:p><w:r><w:t>受访者描述了迁移后的照护变化。</w:t></w:r></w:p>
                <w:tbl><w:tr><w:tc><w:p><w:r><w:t>关系</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>变化</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
              </w:body>
            </w:document>""",
        )
    return output.getvalue()


def _one_page_pdf_bytes() -> bytes:
    # A hand-authored, born-digital PDF keeps this test independent of a PDF
    # writer and makes the expected text/reading order explicit.
    objects = [
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n",
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n",
        (
            b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 300 200] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj\n"
        ),
        b"4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n",
        (
            b"5 0 obj << /Length 47 >> stream\nBT /F1 12 Tf 24 160 Td "
            b"(Interview context) Tj 0 -24 Td (Care changed after migration.) "
            b"Tj ET\nendstream endobj\n"
        ),
    ]
    header = b"%PDF-1.4\n"
    body = bytearray(header)
    offsets = [0]
    for value in objects:
        offsets.append(len(body))
        body.extend(value)
    xref_offset = len(body)
    body.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    body.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        body.extend(f"{offset:010d} 00000 n \n".encode())
    body.extend(
        (
            f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode()
    )
    return bytes(body)


def test_txt_parser_preserves_paragraph_order_and_line_locator() -> None:
    parsed = parse_material(
        filename="field-notes.txt",
        media_type="text/plain",
        content="第一段观察。\n仍是第一段。\n\n第二段观察。\n".encode(),
    )

    assert parsed.full_text == "第一段观察。\n仍是第一段。\n\n第二段观察。"
    assert [block.text for block in parsed.blocks] == ["第一段观察。\n仍是第一段。", "第二段观察。"]
    assert parsed.blocks[0].locator.line_start == 1
    assert parsed.blocks[0].locator.line_end == 2
    assert parsed.blocks[1].locator.paragraph == 2


def test_markdown_parser_preserves_heading_path_and_source_lines() -> None:
    parsed = parse_material(
        filename="notes.md",
        media_type="text/markdown",
        content="# 田野记录\n\n## 夜间会议\n\n参与者在临时群聊中求助。\n".encode(),
    )

    assert [block.kind for block in parsed.blocks] == ["heading", "heading", "paragraph"]
    assert parsed.blocks[2].locator.section_path == ("田野记录", "夜间会议")
    assert parsed.blocks[2].locator.line_start == 5
    assert parsed.blocks[2].locator.line_end == 5


def test_docx_parser_keeps_heading_paragraph_and_table_content() -> None:
    parsed = parse_material(
        filename="interview.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        content=_docx_bytes(),
    )

    assert [block.kind for block in parsed.blocks] == ["heading", "paragraph", "table"]
    assert parsed.blocks[0].text == "访谈主题"
    assert parsed.blocks[1].locator.section_path == ("访谈主题",)
    assert "关系 | 变化" in parsed.blocks[2].text


def test_pdf_parser_keeps_page_locator_and_rejects_empty_extract_without_ocr() -> None:
    parsed = parse_material(
        filename="interview.pdf",
        media_type="application/pdf",
        content=_one_page_pdf_bytes(),
    )

    assert parsed.blocks
    assert parsed.blocks[0].locator.page == 1
    assert "Interview context" in parsed.full_text
    assert "Care changed after migration." in parsed.full_text

    with pytest.raises(MaterialParseError, match="no_extractable_text"):
        parse_material(filename="empty.pdf", media_type="application/pdf", content=b"not a pdf")


def test_parser_rejects_image_media_type_before_any_ocr_path() -> None:
    with pytest.raises(MaterialParseError, match="unsupported_format"):
        parse_material(filename="photo.png", media_type="image/png", content=b"image")


def test_parser_uses_filename_for_missing_or_generic_text_mime() -> None:
    content = "# 观察\n\n参与者在门口停留。".encode()
    for media_type in ("", "application/octet-stream", "text/plain"):
        parsed = parse_material(filename="记录.md", media_type=media_type, content=content)
        assert parsed.structured_document["format"] == "markdown"
