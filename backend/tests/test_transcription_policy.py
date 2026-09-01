from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

import pytest

from qunxue_api.application.transcription import TranscriptionApplication
from qunxue_api.modules.research_materials import (
    ConsentScope,
    DeidentificationStatus,
    MaterialArchiveProfile,
    MaterialKind,
    ModelProcessingScope,
    ResearchMaterial,
)
from qunxue_api.modules.transcription import (
    ParsedTranscript,
    ProcessingLocation,
    TranscriptionError,
    TranscriptionPolicyDenied,
    TranscriptionStatus,
    TranscriptSegment,
)

NOW = datetime(2026, 9, 1, 10, tzinfo=UTC)


class _Tasks:
    def get(self, _task_id: UUID, _user_id: UUID) -> object:
        return object()


class _Materials:
    def __init__(self, material: ResearchMaterial) -> None:
        self.material = material
        self.read_count = 0
        self.parse_versions: list[object] = []

    def get(self, *_args: object, **_kwargs: object) -> ResearchMaterial:
        return self.material

    def get_original(self, *_args: object, **_kwargs: object) -> bytes:
        self.read_count += 1
        return b"media"

    def reserve_reparse(self, *_args: object, **kwargs: object) -> object:
        return SimpleNamespace(parse_id=kwargs["parse_id"])

    def begin_reparse(self, *_args: object, **kwargs: object) -> ResearchMaterial:
        self.material = replace(
            self.material,
            status="parsing",
            current_parse_id=kwargs["parse_id"],
            updated_at=kwargs["now"],
        )
        return self.material

    def list_parses(self, *_args: object, **_kwargs: object) -> tuple[object, ...]:
        return tuple(self.parse_versions)

    def save_parse(self, parsed: object) -> object:
        self.parse_versions.append(parsed)
        self.material = replace(
            self.material,
            status=parsed.status,
            last_error_code=parsed.error_code,
            updated_at=parsed.completed_at,
        )
        return parsed


class _Archive:
    def __init__(self, profile: MaterialArchiveProfile) -> None:
        self.profile = profile

    def get_profile(self, *_args: object, **_kwargs: object) -> MaterialArchiveProfile:
        return self.profile


class _ExternalProvider:
    available = True
    name = "existing-service"
    processing_location = ProcessingLocation.EXTERNAL

    def transcribe(self, **_kwargs: object) -> ParsedTranscript:
        return ParsedTranscript(
            source_format="json",
            segments=(TranscriptSegment(ordinal=0, text="不会被调用", start_ms=0, end_ms=1),),
        )


class _FailingExternalProvider(_ExternalProvider):
    def transcribe(self, **_kwargs: object) -> ParsedTranscript:
        raise TranscriptionError("provider failed")


def test_external_provider_is_denied_before_media_bytes_are_read() -> None:
    material = ResearchMaterial.create(
        user_id=UUID(int=1),
        task_id=UUID(int=2),
        idempotency_key="media",
        original_filename="访谈.wav",
        media_type="audio/wav",
        content=b"media",
        material_kind=MaterialKind.INTERVIEW_TRANSCRIPT,
        now=NOW,
    )
    materials = _Materials(material)
    profile = MaterialArchiveProfile.create(
        material_id=material.material_id,
        user_id=material.user_id,
        task_id=material.task_id,
        consent_scope=ConsentScope.PROJECT_ONLY,
        deidentification_status=DeidentificationStatus.PENDING,
        model_processing_scope=ModelProcessingScope.NOT_ASSESSED,
        now=NOW,
    )
    application = TranscriptionApplication(
        materials=materials,  # type: ignore[arg-type]
        archive=_Archive(profile),  # type: ignore[arg-type]
        research_tasks=_Tasks(),  # type: ignore[arg-type]
        provider=_ExternalProvider(),
        importer=lambda **_kwargs: None,  # type: ignore[arg-type]
    )

    with pytest.raises(TranscriptionPolicyDenied):
        application.transcribe(
            user_id=material.user_id,
            task_id=material.task_id,
            material_id=material.material_id,
            idempotency_key="run",
        )

    assert materials.read_count == 0


def test_provider_failure_is_persisted_without_losing_the_media() -> None:
    material = ResearchMaterial.create(
        user_id=UUID(int=11),
        task_id=UUID(int=12),
        idempotency_key="media-failure",
        original_filename="访谈.wav",
        media_type="audio/wav",
        content=b"media",
        material_kind=MaterialKind.INTERVIEW_TRANSCRIPT,
        now=NOW,
    )
    materials = _Materials(material)
    profile = MaterialArchiveProfile.create(
        material_id=material.material_id,
        user_id=material.user_id,
        task_id=material.task_id,
        consent_scope=ConsentScope.PROJECT_ONLY,
        deidentification_status=DeidentificationStatus.COMPLETE,
        model_processing_scope=ModelProcessingScope.EXTERNAL_ALLOWED,
        now=NOW,
    )
    commits: list[str] = []
    application = TranscriptionApplication(
        materials=materials,  # type: ignore[arg-type]
        archive=_Archive(profile),  # type: ignore[arg-type]
        research_tasks=_Tasks(),  # type: ignore[arg-type]
        provider=_FailingExternalProvider(),
        importer=lambda **_kwargs: None,  # type: ignore[arg-type]
        clock=lambda: NOW,
        commit=lambda: commits.append("committed"),
    )

    with pytest.raises(TranscriptionError):
        application.transcribe(
            user_id=material.user_id,
            task_id=material.task_id,
            material_id=material.material_id,
            idempotency_key="failed-run",
        )

    workspace = application.workspace(
        user_id=material.user_id,
        task_id=material.task_id,
        material_id=material.material_id,
    )
    assert workspace.status is TranscriptionStatus.FAILED
    assert workspace.error_code == "transcription_provider_failed"
    assert materials.read_count == 1
    assert commits == ["committed", "committed"]
