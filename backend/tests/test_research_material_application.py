from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

from qunxue_api.application.research_materials import ResearchMaterialApplication
from qunxue_api.modules.research_materials import (
    MaterialBlock,
    MaterialKind,
    MaterialLocator,
    ParsedMaterial,
    ResearchMaterial,
)


class _TaskRepository:
    def get(self, _task_id: UUID, _user_id: UUID) -> object:
        return object()


class _MaterialRepository:
    def __init__(self, material: ResearchMaterial) -> None:
        self.material = material
        self.parse_versions = []

    def create(self, **_kwargs: object) -> ResearchMaterial:
        return self.material

    def begin_reparse(self, material_id: UUID, **kwargs: object) -> ResearchMaterial:
        self.material = replace(
            self.material,
            status="parsing",
            current_parse_id=kwargs["parse_id"],
            updated_at=kwargs["now"],
        )
        return self.material

    def list_parses(self, _material_id: UUID, **_kwargs: object) -> tuple[object, ...]:
        return tuple(self.parse_versions)

    def save_parse(self, parsed: object) -> object:
        self.parse_versions.append(parsed)
        self.material = replace(
            self.material,
            status="ready",
            current_parse_id=parsed.parse_id,
            current_parse_version=parsed.version,
            updated_at=parsed.completed_at,
        )
        return parsed

    def get(self, _material_id: UUID, **_kwargs: object) -> ResearchMaterial:
        return self.material


def test_upload_commits_before_returning_so_follow_up_reads_see_the_material() -> None:
    user_id = UUID(int=1)
    task_id = UUID(int=2)
    now = datetime(2026, 8, 29, 12, tzinfo=UTC)
    material = ResearchMaterial.create(
        material_id=UUID(int=3),
        user_id=user_id,
        task_id=task_id,
        idempotency_key="upload-1",
        original_filename="访谈.txt",
        media_type="text/plain",
        content="一段访谈记录".encode(),
        material_kind=MaterialKind.INTERVIEW_TRANSCRIPT,
        now=now,
    )
    repository = _MaterialRepository(material)
    commits: list[str] = []

    def parser(**kwargs: object) -> ParsedMaterial:
        parse_id = kwargs["parse_id"]
        block = MaterialBlock.create(
            parse_id=parse_id,
            material_id=material.material_id,
            ordinal=0,
            kind="paragraph",
            text="一段访谈记录",
            locator=MaterialLocator(paragraph=1, char_start=0, char_end=6),
        )
        return ParsedMaterial(
            full_text=block.text,
            structured_document={},
            blocks=(block,),
            content_hash=block.content_hash,
            parser_name="test-parser",
            parser_version="1",
            schema_version="1",
        )

    application = ResearchMaterialApplication(
        materials=repository,  # type: ignore[arg-type]
        research_tasks=_TaskRepository(),  # type: ignore[arg-type]
        parser=parser,
        clock=lambda: now,
        commit=lambda: commits.append("committed"),
    )

    application.upload(
        user_id=user_id,
        task_id=task_id,
        idempotency_key="upload-1",
        filename="访谈.txt",
        media_type="text/plain",
        content="一段访谈记录".encode(),
        material_kind=MaterialKind.INTERVIEW_TRANSCRIPT,
    )

    assert commits == ["committed"]
