"""Task-owned media transcription, import, and correction workflow."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

from qunxue_api.modules.research_intake import ResearchTaskRepository
from qunxue_api.modules.research_materials import (
    MaterialArchiveProfile,
    MaterialBlock,
    MaterialLocator,
    MaterialNotFound,
    MaterialParseVersion,
    MaterialStatus,
    ModelProcessingScope,
    ProfessionalMaterialRepository,
    ResearchMaterial,
    ResearchMaterialRepository,
)
from qunxue_api.modules.transcription import (
    ParsedTranscript,
    ProcessingLocation,
    TranscriptionError,
    TranscriptionPolicyDenied,
    TranscriptionProvider,
    TranscriptionStatus,
    TranscriptionUnavailable,
    TranscriptionWorkspace,
    TranscriptSegment,
    TranscriptSource,
    TranscriptVersion,
    TranscriptVersionConflict,
    UnsupportedTranscriptImport,
)

_TRANSCRIPT_SCHEMA = "transcript.v1"


class TranscriptionApplication:
    def __init__(
        self,
        *,
        materials: ResearchMaterialRepository,
        archive: ProfessionalMaterialRepository,
        research_tasks: ResearchTaskRepository,
        provider: TranscriptionProvider,
        importer: Callable[..., ParsedTranscript],
        clock: Callable[[], datetime] | None = None,
        commit: Callable[[], None] | None = None,
    ) -> None:
        self._materials = materials
        self._archive = archive
        self._research_tasks = research_tasks
        self._provider = provider
        self._importer = importer
        self._clock = clock or (lambda: datetime.now(UTC))
        self._commit = commit or (lambda: None)

    def workspace(
        self, *, user_id: UUID, task_id: UUID, material_id: UUID
    ) -> TranscriptionWorkspace:
        material = self._media(user_id=user_id, task_id=task_id, material_id=material_id)
        versions = self._versions(material=material, user_id=user_id, task_id=task_id)
        current = next((item for item in versions if item.is_current), None)
        if material.status is MaterialStatus.PARSING:
            status = TranscriptionStatus.PROCESSING
        elif material.status is MaterialStatus.FAILED:
            status = TranscriptionStatus.FAILED
        elif current is not None:
            status = TranscriptionStatus.READY
        elif self._provider.available:
            status = TranscriptionStatus.NOT_STARTED
        else:
            status = TranscriptionStatus.UNAVAILABLE
        return TranscriptionWorkspace(
            material_id=material.material_id,
            status=status,
            automatic_available=self._provider.available,
            automatic_provider=self._provider.name,
            current_version=current,
            versions=versions,
            error_code=material.last_error_code,
        )

    def import_transcript(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        material_id: UUID,
        idempotency_key: str,
        filename: str,
        media_type: str | None,
        content: bytes,
    ) -> TranscriptVersion:
        material = self._media(user_id=user_id, task_id=task_id, material_id=material_id)
        self._require_manual_access(material)
        try:
            parsed = self._importer(
                filename=filename,
                media_type=media_type,
                content=content,
            )
        except (TypeError, ValueError) as error:
            raise UnsupportedTranscriptImport(str(error)) from error
        return self._save_version(
            material=material,
            user_id=user_id,
            task_id=task_id,
            idempotency_key=idempotency_key,
            parsed=parsed,
            source=TranscriptSource.IMPORTED,
            provider=None,
            created_from_version_id=None,
        )

    def revise(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        material_id: UUID,
        idempotency_key: str,
        base_version_id: UUID,
        segments: tuple[TranscriptSegment, ...],
    ) -> TranscriptVersion:
        material = self._media(user_id=user_id, task_id=task_id, material_id=material_id)
        self._require_manual_access(material)
        if material.current_parse_id != base_version_id:
            raise TranscriptVersionConflict("transcript was updated from another version")
        base = self._materials.get_parse(
            material_id,
            base_version_id,
            user_id=user_id,
            task_id=task_id,
        )
        if base is None or base.schema_version != _TRANSCRIPT_SCHEMA:
            raise MaterialNotFound(str(base_version_id))
        parsed = ParsedTranscript(source_format="manual", segments=segments)
        return self._save_version(
            material=material,
            user_id=user_id,
            task_id=task_id,
            idempotency_key=idempotency_key,
            parsed=parsed,
            source=TranscriptSource.MANUAL_CORRECTION,
            provider=None,
            created_from_version_id=base_version_id,
        )

    def transcribe(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        material_id: UUID,
        idempotency_key: str,
    ) -> TranscriptVersion:
        material = self._media(user_id=user_id, task_id=task_id, material_id=material_id)
        if not self._provider.available:
            raise TranscriptionUnavailable("automatic transcription is not configured")
        self._require_provider_access(material)
        content = self._materials.get_original(
            material_id,
            user_id=user_id,
            task_id=task_id,
        )
        if content is None:
            raise MaterialNotFound(str(material_id))
        prepared = self._begin_version(
            material=material,
            user_id=user_id,
            task_id=task_id,
            idempotency_key=idempotency_key,
        )
        if isinstance(prepared, TranscriptVersion):
            return prepared
        candidate_id, version_number = prepared
        try:
            parsed = self._provider.transcribe(
                filename=material.original_filename,
                media_type=material.media_type,
                content=content,
            )
        except TranscriptionError:
            failed = MaterialParseVersion.failed(
                parse_id=candidate_id,
                material_id=material.material_id,
                version=version_number,
                parser_name=self._provider.name,
                parser_version="1.0",
                schema_version=_TRANSCRIPT_SCHEMA,
                error_code="transcription_provider_failed",
                now=self._clock(),
            )
            self._materials.save_parse(failed)
            self._commit()
            raise
        return self._persist_version(
            material=material,
            candidate_id=candidate_id,
            version_number=version_number,
            parsed=parsed,
            source=TranscriptSource.AUTOMATIC,
            provider=self._provider.name,
            created_from_version_id=None,
        )

    def _save_version(
        self,
        *,
        material: ResearchMaterial,
        user_id: UUID,
        task_id: UUID,
        idempotency_key: str,
        parsed: ParsedTranscript,
        source: TranscriptSource,
        provider: str | None,
        created_from_version_id: UUID | None,
    ) -> TranscriptVersion:
        prepared = self._begin_version(
            material=material,
            user_id=user_id,
            task_id=task_id,
            idempotency_key=idempotency_key,
        )
        if isinstance(prepared, TranscriptVersion):
            return prepared
        candidate_id, version_number = prepared
        return self._persist_version(
            material=material,
            candidate_id=candidate_id,
            version_number=version_number,
            parsed=parsed,
            source=source,
            provider=provider,
            created_from_version_id=created_from_version_id,
        )

    def _begin_version(
        self,
        *,
        material: ResearchMaterial,
        user_id: UUID,
        task_id: UUID,
        idempotency_key: str,
    ) -> tuple[UUID, int] | TranscriptVersion:
        candidate_id = uuid4()
        request = self._materials.reserve_reparse(
            material.material_id,
            user_id=user_id,
            task_id=task_id,
            idempotency_key=idempotency_key,
            parse_id=candidate_id,
            now=self._clock(),
        )
        if request.parse_id != candidate_id:
            replay = self._materials.get_parse(
                material.material_id,
                request.parse_id,
                user_id=user_id,
                task_id=task_id,
            )
            if replay is None or replay.status is not MaterialStatus.READY:
                raise TranscriptVersionConflict("transcript request is still being processed")
            current = self._materials.get(
                material.material_id,
                user_id=user_id,
                task_id=task_id,
            )
            return self._from_parse(
                replay,
                current_id=current.current_parse_id if current is not None else None,
            )
        self._materials.begin_reparse(
            material.material_id,
            user_id=user_id,
            task_id=task_id,
            parse_id=candidate_id,
            now=self._clock(),
            expected_current_version=material.current_parse_version,
        )
        # Persist the processing state before any external provider call can
        # block. Imports and corrections also use this transaction boundary so
        # every completed version follows the same append-only path.
        self._commit()
        existing = self._materials.list_parses(
            material.material_id,
            user_id=user_id,
            task_id=task_id,
        )
        version_number = max((item.version for item in existing), default=0) + 1
        return candidate_id, version_number

    def _persist_version(
        self,
        *,
        material: ResearchMaterial,
        candidate_id: UUID,
        version_number: int,
        parsed: ParsedTranscript,
        source: TranscriptSource,
        provider: str | None,
        created_from_version_id: UUID | None,
    ) -> TranscriptVersion:
        blocks = tuple(
            MaterialBlock.create(
                parse_id=candidate_id,
                material_id=material.material_id,
                ordinal=item.ordinal,
                kind="transcript_segment",
                text=item.text,
                segment_id=item.segment_id,
                locator=MaterialLocator(
                    block_index=item.ordinal,
                    time_start_ms=item.start_ms,
                    time_end_ms=item.end_ms,
                    speaker=item.speaker,
                ),
            )
            for item in parsed.segments
        )
        full_text = "\n\n".join(
            f"{item.speaker}：{item.text}" if item.speaker else item.text
            for item in parsed.segments
        )
        parse = MaterialParseVersion.create(
            parse_id=candidate_id,
            material_id=material.material_id,
            version=version_number,
            parser_name=provider or "qunxue-transcript-import",
            parser_version="1.0",
            schema_version=_TRANSCRIPT_SCHEMA,
            full_text=full_text,
            structured_document={
                "kind": "transcript",
                "source": source.value,
                "source_format": parsed.source_format,
                "provider": provider,
                "created_from_version_id": (
                    str(created_from_version_id) if created_from_version_id else None
                ),
            },
            blocks=blocks,
            now=self._clock(),
        )
        self._materials.save_parse(parse)
        self._commit()
        return self._from_parse(parse, current_id=parse.parse_id)

    def _versions(
        self, *, material: ResearchMaterial, user_id: UUID, task_id: UUID
    ) -> tuple[TranscriptVersion, ...]:
        values = (
            self._from_parse(item, current_id=material.current_parse_id)
            for item in self._materials.list_parses(
                material.material_id,
                user_id=user_id,
                task_id=task_id,
            )
            if item.status is MaterialStatus.READY and item.schema_version == _TRANSCRIPT_SCHEMA
        )
        return tuple(sorted(values, key=lambda item: item.version, reverse=True))

    @staticmethod
    def _from_parse(
        parsed: MaterialParseVersion, *, current_id: UUID | None
    ) -> TranscriptVersion:
        metadata = parsed.structured_document
        source = TranscriptSource(str(metadata.get("source", TranscriptSource.IMPORTED.value)))
        parent = metadata.get("created_from_version_id")
        return TranscriptVersion(
            version_id=parsed.parse_id,
            material_id=parsed.material_id,
            version=parsed.version,
            source=source,
            provider=(str(metadata["provider"]) if metadata.get("provider") else None),
            created_from_version_id=UUID(str(parent)) if parent else None,
            segments=tuple(
                TranscriptSegment(
                    segment_id=block.segment_id,
                    ordinal=block.ordinal,
                    text=block.text,
                    start_ms=block.locator.time_start_ms,
                    end_ms=block.locator.time_end_ms,
                    speaker=block.locator.speaker,
                )
                for block in parsed.blocks
            ),
            created_at=parsed.created_at,
            is_current=parsed.parse_id == current_id,
        )

    def _media(self, *, user_id: UUID, task_id: UUID, material_id: UUID) -> ResearchMaterial:
        if self._research_tasks.get(task_id, user_id) is None:
            from qunxue_api.modules.research_intake import ResearchTaskNotFound

            raise ResearchTaskNotFound(str(task_id))
        material = self._materials.get(material_id, user_id=user_id, task_id=task_id)
        if material is None or not material.material_format.is_media:
            raise MaterialNotFound(str(material_id))
        return material

    def _profile(self, material: ResearchMaterial) -> MaterialArchiveProfile | None:
        return self._archive.get_profile(
            material.material_id,
            user_id=material.user_id,
            task_id=material.task_id,
        )

    def _require_manual_access(self, material: ResearchMaterial) -> None:
        profile = self._profile(material)
        if profile is not None and not profile.allows_manual_reading:
            raise TranscriptionPolicyDenied("material consent was withdrawn")

    def _require_provider_access(self, material: ResearchMaterial) -> None:
        profile = self._profile(material)
        if profile is None:
            return
        if self._provider.processing_location is ProcessingLocation.EXTERNAL:
            if not profile.allows_external_model_processing:
                raise TranscriptionPolicyDenied("external model processing is not allowed")
            return
        if (
            not profile.allows_manual_reading
            or profile.model_processing_scope
            not in {ModelProcessingScope.LOCAL_ONLY, ModelProcessingScope.EXTERNAL_ALLOWED}
        ):
            raise TranscriptionPolicyDenied("local model processing is not allowed")
