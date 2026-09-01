from datetime import UTC, datetime
from uuid import UUID

import pytest

from qunxue_api.modules.research_materials import (
    MaterialBlock,
    MaterialFormat,
    MaterialKind,
    MaterialLocator,
    MaterialParseVersion,
    MaterialStatus,
    ResearchMaterial,
    UnsupportedMaterialFormat,
)


def test_supported_formats_are_limited_to_research_documents_without_images() -> None:
    assert MaterialFormat.from_media_type("application/pdf") is MaterialFormat.PDF
    assert (
        MaterialFormat.from_media_type(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        is MaterialFormat.DOCX
    )
    assert MaterialFormat.from_media_type("text/plain") is MaterialFormat.TXT
    assert MaterialFormat.from_media_type("text/markdown") is MaterialFormat.MARKDOWN

    with pytest.raises(UnsupportedMaterialFormat):
        MaterialFormat.from_media_type("image/png")

    with pytest.raises(UnsupportedMaterialFormat):
        MaterialFormat.from_media_type("application/octet-stream")


def test_audio_and_video_formats_are_media_materials_without_accepting_images() -> None:
    assert (
        MaterialFormat.resolve(filename="访谈.mp3", media_type="audio/mpeg") is MaterialFormat.MP3
    )
    assert (
        MaterialFormat.resolve(filename="焦点小组.m4a", media_type="audio/mp4")
        is MaterialFormat.M4A
    )
    assert (
        MaterialFormat.resolve(filename="观察录像.mp4", media_type="video/mp4")
        is MaterialFormat.MP4
    )
    assert (
        MaterialFormat.resolve(filename="线上访谈.webm", media_type="video/webm")
        is MaterialFormat.WEBM
    )
    assert MaterialFormat.MP3.is_media is True
    assert MaterialFormat.PDF.is_media is False

    with pytest.raises(UnsupportedMaterialFormat):
        MaterialFormat.resolve(filename="现场.png", media_type="image/png")


def test_media_locator_round_trips_original_timecode_and_speaker() -> None:
    locator = MaterialLocator(
        time_start_ms=1_250,
        time_end_ms=3_800,
        speaker="主持人",
    )

    assert MaterialLocator.from_dict(locator.as_dict()) == locator
    assert locator.display() == "00:01.250-00:03.800，主持人"


def test_legacy_observation_kind_is_normalized_to_observation_record() -> None:
    assert MaterialKind("observation") is MaterialKind.OBSERVATION_RECORD


def test_ambiguous_upload_mime_is_canonicalized_from_filename() -> None:
    material = ResearchMaterial.create(
        user_id=UUID(int=2),
        task_id=UUID(int=3),
        idempotency_key="upload-md",
        original_filename="记录.md",
        media_type="text/plain",
        content="# 标题".encode(),
        material_kind="observation",  # type: ignore[arg-type]
        now=datetime(2026, 8, 29, 12, 0, tzinfo=UTC),
    )

    assert material.material_format is MaterialFormat.MARKDOWN
    assert material.media_type == "text/markdown"
    assert material.material_kind is MaterialKind.OBSERVATION_RECORD


def test_material_creation_starts_uploaded_and_records_owned_file_metadata() -> None:
    now = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)
    material = ResearchMaterial.create(
        material_id=UUID(int=1),
        user_id=UUID(int=2),
        task_id=UUID(int=3),
        idempotency_key="upload-1",
        original_filename="访谈记录.docx",
        media_type=("application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        content=b"raw-docx",
        material_kind=MaterialKind.INTERVIEW_TRANSCRIPT,
        now=now,
    )

    assert material.status is MaterialStatus.UPLOADED
    assert material.size_bytes == 8
    assert material.content_hash == (
        "36d5a9996f59c1c162ff82a6dcc7b9cb6be47dfdc4e70db82ffeda88889ca5be"
    )
    assert material.current_parse_id is None
    assert material.current_parse_version is None
    assert material.original_filename == "访谈记录.docx"
    assert material.user_id == UUID(int=2)
    assert material.task_id == UUID(int=3)


def test_parse_version_has_stable_block_locators_and_deterministic_ids() -> None:
    material_id = UUID(int=10)
    parse_id = UUID(int=11)
    locator = MaterialLocator(
        page=4,
        section_path=("访谈", "家庭迁移"),
        paragraph=2,
        char_start=15,
        char_end=42,
    )
    first = MaterialBlock.create(
        parse_id=parse_id,
        material_id=material_id,
        ordinal=0,
        kind="paragraph",
        text="受访者描述了迁移后的照护变化。",
        locator=locator,
    )
    second = MaterialBlock.create(
        parse_id=parse_id,
        material_id=material_id,
        ordinal=0,
        kind="paragraph",
        text="受访者描述了迁移后的照护变化。",
        locator=locator,
    )
    assert first.block_id == second.block_id
    assert first.content_hash == second.content_hash
    assert first.locator == locator
    assert first.locator.as_dict() == {
        "page": 4,
        "section_path": ["访谈", "家庭迁移"],
        "paragraph": 2,
        "line_start": None,
        "line_end": None,
        "char_start": 15,
        "char_end": 42,
        "block_index": None,
        "time_start_ms": None,
        "time_end_ms": None,
        "speaker": None,
    }

    parsed = MaterialParseVersion.create(
        parse_id=parse_id,
        material_id=material_id,
        version=1,
        parser_name="test-parser",
        parser_version="1.0",
        schema_version="1",
        full_text=first.text,
        structured_document={"title": "访谈"},
        blocks=(first,),
        content_hash=first.content_hash,
        now=datetime(2026, 8, 29, 12, 1, tzinfo=UTC),
    )
    assert parsed.status is MaterialStatus.READY
    assert parsed.blocks == (first,)


def test_failed_reparse_does_not_replace_last_ready_parse() -> None:
    ready = ResearchMaterial(
        material_id=UUID(int=20),
        user_id=UUID(int=21),
        task_id=UUID(int=22),
        idempotency_key="upload-20",
        original_filename="notes.md",
        display_name="notes.md",
        media_type="text/markdown",
        material_format=MaterialFormat.MARKDOWN,
        material_kind=MaterialKind.FIELD_NOTE,
        size_bytes=4,
        content_hash="a" * 64,
        status=MaterialStatus.READY,
        current_parse_id=UUID(int=23),
        current_parse_version=1,
        processing_policy_version="2026-08-29",
        created_at=datetime(2026, 8, 29, 12, tzinfo=UTC),
        updated_at=datetime(2026, 8, 29, 12, 2, tzinfo=UTC),
    )
    reparsing = ready.begin_reparse(
        parse_id=UUID(int=24),
        now=datetime(2026, 8, 29, 12, 3, tzinfo=UTC),
    )
    failed = reparsing.fail_parse(
        parse_id=UUID(int=24),
        error_code="parse_failed",
        now=datetime(2026, 8, 29, 12, 4, tzinfo=UTC),
    )

    assert failed.status is MaterialStatus.FAILED
    assert failed.current_parse_id == UUID(int=23)
    assert failed.current_parse_version == 1
    assert failed.last_error_code == "parse_failed"


def test_successful_parse_requires_at_least_one_locatable_block() -> None:
    with pytest.raises(ValueError, match="at least one source block"):
        MaterialParseVersion.create(
            parse_id=UUID(int=25),
            material_id=UUID(int=26),
            version=1,
            parser_name="test-parser",
            parser_version="1.0",
            schema_version="1",
            full_text="存在正文但没有可引用位置",
            structured_document={},
            blocks=(),
            now=datetime(2026, 8, 29, 12, 5, tzinfo=UTC),
        )


def test_deleting_material_creates_tombstone_without_retaining_content() -> None:
    material = ResearchMaterial(
        material_id=UUID(int=30),
        user_id=UUID(int=31),
        task_id=UUID(int=32),
        idempotency_key="upload-30",
        original_filename="paper.pdf",
        display_name="paper.pdf",
        media_type="application/pdf",
        material_format=MaterialFormat.PDF,
        material_kind=MaterialKind.PAPER,
        size_bytes=100,
        content_hash="b" * 64,
        status=MaterialStatus.READY,
        current_parse_id=UUID(int=33),
        current_parse_version=1,
        processing_policy_version="2026-08-29",
        created_at=datetime(2026, 8, 29, 12, tzinfo=UTC),
        updated_at=datetime(2026, 8, 29, 12, 2, tzinfo=UTC),
    )
    deleted = material.delete(now=datetime(2026, 8, 29, 12, 5, tzinfo=UTC))

    assert deleted.status is MaterialStatus.DELETED
    assert deleted.current_parse_id is None
    assert deleted.current_parse_version is None
    assert deleted.deleted_at == datetime(2026, 8, 29, 12, 5, tzinfo=UTC)
    assert deleted.last_error_code is None
