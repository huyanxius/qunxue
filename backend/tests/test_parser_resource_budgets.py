from collections import Counter
from io import BytesIO
from uuid import uuid4
from zipfile import ZipExtFile, ZipFile

import pytest
from fastapi.testclient import TestClient
from pypdf import PageObject, PdfReader, PdfWriter
from test_qdpx_exchange import FIXTURE as QDPX_FIXTURE
from test_qdpx_exchange import _social_research_project
from test_research_material_parsing import _docx_bytes, _one_page_pdf_bytes
from test_research_project_exchange_api import _create_existing_research, _register
from test_shared_knowledge_pptx import pptx_fixture

from qunxue_api.adapters.research_materials import parser
from qunxue_api.modules.research_exchange import export_qdpx, import_qdpx, qdpx
from qunxue_api.modules.research_materials import MaterialBlock, MaterialParseError


@pytest.fixture
def member_reads(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    reads: list[str] = []
    read = ZipExtFile.read

    def record(member: ZipExtFile, n: int = -1) -> bytes:
        reads.append(member.name)
        return read(member, n)

    monkeypatch.setattr(ZipExtFile, "read", record)
    return reads


def _parse_error_code(filename: str, content: bytes) -> str | None:
    try:
        parser.parse_material(filename=filename, media_type=None, content=content)
    except MaterialParseError as error:
        return error.code
    return None


@pytest.mark.parametrize("limit", ["member", "expanded", "members"])
def test_docx_checks_zip_budget_before_reading_xml(monkeypatch, member_reads, limit) -> None:
    content = BytesIO(_docx_bytes())
    namespace = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    styles = "".join(
        f'<w:style w:type="paragraph" w:styleId="Heading{i}"><w:name w:val="heading {i}"/>'
        "</w:style>"
        for i in range(1, 9)
    )
    with ZipFile(content, "a") as archive:
        archive.writestr("word/styles.xml", f'<w:styles xmlns:w="{namespace}">{styles}</w:styles>')
        document_bytes = archive.getinfo("word/document.xml").file_size
        styles_bytes = archive.getinfo("word/styles.xml").file_size

    # With ordinary limits this fixture includes a heading, a paragraph, and a table.
    payload = content.getvalue()
    parsed = parser.parse_material(filename="notes.docx", media_type=None, content=payload)
    assert [block.kind for block in parsed.blocks] == ["heading", "paragraph", "table"]
    member_reads.clear()

    name, value = {
        "member": ("_MAX_ZIP_MEMBER_BYTES", styles_bytes - 1),
        "expanded": ("_MAX_ZIP_EXPANDED_BYTES", document_bytes + styles_bytes - 1),
        "members": ("_MAX_ZIP_MEMBERS", 1),
    }[limit]
    assert document_bytes < styles_bytes
    monkeypatch.setattr(parser, name, value, raising=False)

    assert (_parse_error_code("notes.docx", payload), member_reads) == (
        "document_too_large",
        [],
    )


@pytest.mark.parametrize("limit", ["expanded", "pages"])
def test_pptx_checks_budget_before_reading_slides(monkeypatch, member_reads, limit) -> None:
    content = pptx_fixture()
    metadata = ["ppt/presentation.xml", "ppt/_rels/presentation.xml.rels"]
    with ZipFile(BytesIO(content)) as archive:
        metadata_bytes = sum(archive.getinfo(name).file_size for name in metadata)
        visible_slide_bytes = archive.getinfo("ppt/slides/slide2.xml").file_size

    name, value = {
        "expanded": ("_MAX_ZIP_EXPANDED_BYTES", metadata_bytes + visible_slide_bytes),
        "pages": ("_MAX_DOCUMENT_PAGES", 1),
    }[limit]
    monkeypatch.setattr(parser, name, value, raising=False)

    assert (_parse_error_code("slides.pptx", content), member_reads) == (
        "document_too_large",
        metadata,
    )


@pytest.mark.parametrize(
    ("limit", "maximum", "expected_counts"),
    [
        ("_MAX_DOCUMENT_PAGES", 1, (2, 0, 0)),
        ("_MAX_DOCUMENT_BLOCKS", 1, (4, 1, 1)),
        (
            "_MAX_DOCUMENT_TEXT_CHARS",
            len("Interview context\n\nCare changed after migration."),
            (4, 2, 2),
        ),
    ],
    ids=["pages", "blocks", "text"],
)
def test_pdf_stops_at_first_over_budget_page_or_output(
    monkeypatch, limit, maximum, expected_counts
) -> None:
    reader = PdfReader(BytesIO(_one_page_pdf_bytes()))
    writer = PdfWriter()
    for _ in range(4):
        writer.add_page(reader.pages[0])
    output = BytesIO()
    writer.write(output)

    scanned = extracted = created = 0
    init_page = PageObject.__init__
    extract_text = PageObject.extract_text
    create_block = MaterialBlock.create

    def scan(page, *args, **kwargs) -> None:
        nonlocal scanned
        scanned += 1
        init_page(page, *args, **kwargs)

    def extract(page, *args, **kwargs) -> str:
        nonlocal extracted
        extracted += 1
        return extract_text(page, *args, **kwargs)

    def create(*args, **kwargs) -> MaterialBlock:
        nonlocal created
        created += 1
        return create_block(*args, **kwargs)

    monkeypatch.setattr(PageObject, "__init__", scan)
    monkeypatch.setattr(PageObject, "extract_text", extract)
    monkeypatch.setattr(MaterialBlock, "create", create)
    monkeypatch.setattr(parser, limit, maximum, raising=False)

    error_code = _parse_error_code("notes.pdf", output.getvalue())
    assert (error_code, (scanned, extracted, created)) == ("document_too_large", expected_counts)


@pytest.mark.parametrize("filename", ["notes.txt", "notes.md"])
def test_text_formats_share_the_block_budget(monkeypatch, filename) -> None:
    monkeypatch.setattr(parser, "_MAX_DOCUMENT_BLOCKS", 1, raising=False)
    assert _parse_error_code(filename, b"First observation.\n\nSecond observation.") == (
        "document_too_large"
    )


def test_qdpx_import_reads_each_member_once(member_reads) -> None:
    payload = QDPX_FIXTURE.read_bytes()
    with ZipFile(BytesIO(payload)) as archive:
        members = archive.namelist()

    imported = import_qdpx(payload)

    assert imported.project.name == "社区照护田野研究"
    assert imported.project.sources[0].plain_text
    assert Counter(member_reads) == Counter(members)


def test_qdpx_export_keeps_its_budget_when_the_import_budget_is_lower(monkeypatch) -> None:
    monkeypatch.setattr(qdpx, "_MAX_ARCHIVE_BYTES", 1)

    payload = export_qdpx(_social_research_project()).payload

    with pytest.raises(ValueError, match="uncompressed size limit"):
        import_qdpx(payload)


@pytest.mark.parametrize("over_budget", [False, True], ids=["single-read", "expanded"])
def test_qdpx_preview_checks_budget_and_reads_members_once(
    client: TestClient, monkeypatch, member_reads, over_budget
) -> None:
    payload = QDPX_FIXTURE.read_bytes()
    with ZipFile(BytesIO(payload)) as archive:
        members = archive.namelist()
        expanded_bytes = sum(member.file_size for member in archive.infolist())
    _register(client)
    task = _create_existing_research(client)
    if over_budget:
        monkeypatch.setattr(qdpx, "_MAX_ARCHIVE_BYTES", expanded_bytes - 1)

    response = client.post(
        f"/api/research-tasks/{task['task_id']}/exchange/qdpx-preview",
        headers={"Idempotency-Key": str(uuid4())},
        files={"file": ("community-care.qdpx", payload, "application/vnd.qdpx")},
    )

    if over_budget:
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"
        assert member_reads == []
    else:
        assert response.status_code == 200
        assert response.json()["project"]["source_count"] == 1
        assert Counter(member_reads) == Counter(members)
