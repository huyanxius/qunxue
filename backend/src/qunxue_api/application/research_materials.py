"""Task-owned application workflow for durable research materials."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from qunxue_api.modules.research_intake import ResearchTaskRepository
from qunxue_api.modules.research_materials import (
    MaterialBlock,
    MaterialFormat,
    MaterialIngestionJob,
    MaterialIngestionStatus,
    MaterialKind,
    MaterialNotFound,
    MaterialParseError,
    MaterialParseVersion,
    MaterialStatus,
    MaterialVersionConflict,
    ParsedMaterial,
    ResearchMaterial,
    ResearchMaterialRepository,
    ResearchMaterialSearchRepository,
    ResearchMaterialSearchResult,
)


class ResearchMaterialApplication:
    """Owns task authorization and the parse/save transaction boundary.

    Parsing is synchronous for the first validated slice.  The interface keeps
    the parser injectable so a stronger parser can replace the deterministic
    adapter after real-material benchmarks without changing the domain or API.
    """

    def __init__(
        self,
        *,
        materials: ResearchMaterialRepository,
        research_tasks: ResearchTaskRepository,
        parser: Callable[..., ParsedMaterial],
        search: ResearchMaterialSearchRepository | None = None,
        transcription_available: bool = False,
        clock: Callable[[], datetime] | None = None,
        commit: Callable[[], None] | None = None,
        rollback: Callable[[], None] | None = None,
    ) -> None:
        self._materials = materials
        self._research_tasks = research_tasks
        self._parser = parser
        self._search = search
        self._transcription_available = transcription_available
        self._clock = clock or (lambda: datetime.now(UTC))
        # A mutation must be visible to the next request before its response
        # is sent.  The bootstrap supplies the transaction commit; tests and
        # alternate adapters can keep the no-op default.
        self._commit = commit or (lambda: None)
        self._rollback = rollback or (lambda: None)

    def upload(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        idempotency_key: str,
        filename: str,
        media_type: str | None,
        content: bytes,
        material_kind: MaterialKind,
        defer_processing: bool = False,
    ) -> ResearchMaterial:
        self._require_task(user_id=user_id, task_id=task_id)
        now = self._clock()
        material = self._materials.create(
            user_id=user_id,
            task_id=task_id,
            idempotency_key=idempotency_key,
            filename=filename,
            media_type=media_type,
            content=content,
            material_kind=material_kind,
            processing_policy_version="research-materials-v1",
            now=now,
        )
        # A replay returns the already completed result instead of generating
        # another immutable parse version for the same upload request.
        if material.current_parse_id is not None:
            self._commit()
            return material
        if material.material_format.is_media:
            # Media is already durable in the material blob store.  A
            # transcription adapter, manual import, or researcher correction
            # creates the first text version later; the document parser must
            # never pretend the binary media itself is parsed text.
            self._commit()
            return material
        if not hasattr(self._materials, "get_material_ingestion"):
            return self._parse_and_save(
                material=material,
                user_id=user_id,
                task_id=task_id,
                content=content,
            )
        job = self._materials.get_material_ingestion(
            material.material_id,
            user_id=user_id,
            task_id=task_id,
        )
        if job is None:
            job = self._materials.enqueue_ingestion(
                material=material,
                parse_id=uuid4(),
                now=now,
            )
        self._commit()
        if defer_processing:
            return material
        self.process_ingestion(job.job_id, map_unavailable_reason=False)
        return self.get(user_id=user_id, task_id=task_id, material_id=material.material_id)

    def get_ingestion(
        self, *, user_id: UUID, task_id: UUID, material_id: UUID
    ) -> MaterialIngestionJob | None:
        self.get(user_id=user_id, task_id=task_id, material_id=material_id)
        return self._materials.get_material_ingestion(
            material_id,
            user_id=user_id,
            task_id=task_id,
        )

    def ingestion_state(
        self, *, user_id: UUID, task_id: UUID, material_id: UUID
    ) -> tuple[MaterialIngestionStatus, MaterialIngestionJob | None, str | None]:
        material = self.get(user_id=user_id, task_id=task_id, material_id=material_id)
        job = self._materials.get_material_ingestion(
            material_id,
            user_id=user_id,
            task_id=task_id,
        )
        if (
            material.status is MaterialStatus.FAILED
            and (job is None or job.ingestion_status is MaterialIngestionStatus.READY)
        ):
            return MaterialIngestionStatus.FAILED, job, material.last_error_code
        if job is not None:
            reason = (
                job.error_code
                if job.ingestion_status is MaterialIngestionStatus.FAILED
                else None
            )
            return job.ingestion_status, job, reason
        if material.status is MaterialStatus.READY:
            return MaterialIngestionStatus.READY, None, None
        if material.material_format.is_media and material.current_parse_id is None:
            reason = (
                "transcription_required"
                if self._transcription_available
                else "transcription_unavailable"
            )
            return MaterialIngestionStatus.FAILED, None, reason
        if material.status is MaterialStatus.FAILED:
            return MaterialIngestionStatus.FAILED, None, material.last_error_code
        return MaterialIngestionStatus.QUEUED, None, None

    def claim_ingestion(
        self,
        job_id: UUID,
        *,
        lease_duration: timedelta = timedelta(minutes=10),
        now: datetime | None = None,
    ) -> MaterialIngestionJob | None:
        claimed_at = now or self._clock()
        job = self._materials.claim_ingestion(
            job_id,
            now=claimed_at,
            lease_expires_at=claimed_at + lease_duration,
        )
        self._commit()
        return job

    def recoverable_ingestion_ids(self, *, now: datetime | None = None) -> tuple[UUID, ...]:
        return self._materials.recoverable_ingestion_ids(now=now or self._clock())

    def get_ingestion_job(self, job_id: UUID) -> MaterialIngestionJob | None:
        return self._materials.get_ingestion(job_id)

    def process_ingestion(
        self,
        job_id: UUID,
        *,
        map_unavailable_reason: bool = True,
    ) -> MaterialIngestionJob | None:
        job = self.claim_ingestion(job_id)
        if job is None:
            return self._materials.get_ingestion(job_id)
        material = self._materials.get(
            job.material_id,
            user_id=job.user_id,
            task_id=job.task_id,
        )
        content = self._materials.get_original(
            job.material_id,
            user_id=job.user_id,
            task_id=job.task_id,
        )
        if material is None or content is None:
            failed = self._materials.fail_ingestion(
                job_id,
                expected_attempt_count=job.attempt_count,
                expected_parse_id=job.parse_id,
                error_code="research_material_not_found",
                retry_at=None,
                now=self._clock(),
            )
            if failed is None:
                self._rollback()
                return self._materials.get_ingestion(job_id)
            self._commit()
            return failed
        try:
            self._parse_and_save(
                material=material,
                user_id=job.user_id,
                task_id=job.task_id,
                content=content,
                parse_id=job.parse_id,
                begin=material.status is not MaterialStatus.PARSING,
                commit=False,
                map_unavailable_reason=map_unavailable_reason,
            )
        except MaterialParseError as error:
            error_code = (
                self._ingestion_error_code(material, error.code)
                if map_unavailable_reason
                else error.code
            )
            failed = self._materials.fail_ingestion(
                job_id,
                expected_attempt_count=job.attempt_count,
                expected_parse_id=job.parse_id,
                error_code=error_code,
                retry_at=None,
                now=self._clock(),
            )
            if failed is None:
                self._rollback()
                return self._materials.get_ingestion(job_id)
            self._commit()
            raise MaterialParseError(error_code, str(error).split(": ", 1)[-1]) from error
        except Exception:
            self._rollback()
            failed_at = self._clock()
            retry_at = (
                failed_at + timedelta(seconds=min(2**job.attempt_count, 30))
                if job.attempt_count < job.max_attempts
                else None
            )
            self._materials.fail_ingestion(
                job_id,
                expected_attempt_count=job.attempt_count,
                expected_parse_id=job.parse_id,
                error_code="ingestion_worker_error",
                retry_at=retry_at,
                now=failed_at,
            )
            self._commit()
            raise
        completed = self._materials.complete_ingestion(
            job_id,
            expected_attempt_count=job.attempt_count,
            expected_parse_id=job.parse_id,
            now=self._clock(),
        )
        if completed is None:
            self._rollback()
            return self._materials.get_ingestion(job_id)
        self._commit()
        return completed

    def list_owned(
        self, *, user_id: UUID, limit: int = 100, offset: int = 0
    ) -> tuple[ResearchMaterial, ...]:
        return self._materials.list_owned(user_id=user_id, limit=limit, offset=offset)

    def list(self, *, user_id: UUID, task_id: UUID) -> tuple[ResearchMaterial, ...]:
        self._require_task(user_id=user_id, task_id=task_id)
        return self._materials.list(user_id=user_id, task_id=task_id)

    def search(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        query: str,
        material_ids: tuple[UUID, ...] = (),
        material_kind: MaterialKind | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> ResearchMaterialSearchResult:
        self._require_task(user_id=user_id, task_id=task_id)
        if self._search is None:
            raise RuntimeError("research material search is unavailable")
        return self._search.search(
            user_id=user_id,
            task_id=task_id,
            query=query,
            material_ids=tuple(dict.fromkeys(material_ids)),
            material_kind=material_kind,
            limit=limit,
            offset=offset,
        )

    def get(
        self, *, user_id: UUID, task_id: UUID, material_id: UUID
    ) -> ResearchMaterial:
        self._require_task(user_id=user_id, task_id=task_id)
        material = self._materials.get(material_id, user_id=user_id, task_id=task_id)
        if material is None:
            raise MaterialNotFound(str(material_id))
        return material

    def get_original(
        self, *, user_id: UUID, task_id: UUID, material_id: UUID
    ) -> tuple[ResearchMaterial, bytes]:
        material = self.get(user_id=user_id, task_id=task_id, material_id=material_id)
        content = self._materials.get_original(
            material_id,
            user_id=user_id,
            task_id=task_id,
        )
        if content is None:
            raise MaterialNotFound(str(material_id))
        return material, content

    def current_segments(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        material_id: UUID,
        parse_id: UUID | None = None,
    ) -> tuple[MaterialBlock, ...]:
        material = self.get(user_id=user_id, task_id=task_id, material_id=material_id)
        resolved_parse_id = parse_id or material.current_parse_id
        if resolved_parse_id is None:
            return ()
        parsed = self._materials.get_parse(
            material_id,
            resolved_parse_id,
            user_id=user_id,
            task_id=task_id,
        )
        if parsed is None:
            raise MaterialNotFound(str(resolved_parse_id))
        return parsed.blocks

    def get_parse(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        material_id: UUID,
        parse_id: UUID | None = None,
    ) -> MaterialParseVersion | None:
        """Return the resolved immutable parse, including historical versions."""

        material = self.get(user_id=user_id, task_id=task_id, material_id=material_id)
        resolved_parse_id = parse_id or material.current_parse_id
        if resolved_parse_id is None:
            return None
        parsed = self._materials.get_parse(
            material_id,
            resolved_parse_id,
            user_id=user_id,
            task_id=task_id,
        )
        if parsed is None:
            raise MaterialNotFound(str(resolved_parse_id))
        return parsed

    def get_segment(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        material_id: UUID,
        segment_id: str,
        parse_id: UUID | None = None,
    ) -> MaterialBlock:
        material = self.get(user_id=user_id, task_id=task_id, material_id=material_id)
        resolved_parse_id = parse_id or material.current_parse_id
        if resolved_parse_id is None:
            raise MaterialNotFound(segment_id)
        block = self._materials.get_segment(
            material_id,
            resolved_parse_id,
            segment_id,
            user_id=user_id,
            task_id=task_id,
        )
        if block is None:
            raise MaterialNotFound(segment_id)
        return block

    def reparse(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        material_id: UUID,
        idempotency_key: str,
    ) -> ResearchMaterial:
        material = self.get(user_id=user_id, task_id=task_id, material_id=material_id)
        content = self._materials.get_original(
            material_id, user_id=user_id, task_id=task_id
        )
        if content is None:
            raise MaterialNotFound(str(material_id))
        candidate_parse_id = uuid4()
        request = self._materials.reserve_reparse(
            material_id,
            user_id=user_id,
            task_id=task_id,
            idempotency_key=idempotency_key,
            parse_id=candidate_parse_id,
            now=self._clock(),
        )
        if request.parse_id != candidate_parse_id:
            previous = self._materials.get_parse(
                material_id,
                request.parse_id,
                user_id=user_id,
                task_id=task_id,
            )
            if previous is None:
                raise MaterialVersionConflict(
                    "the idempotent reparse request is still being processed"
                )
            if previous.status is MaterialStatus.FAILED:
                raise MaterialParseError(
                    previous.error_code or "research_material_parse_error",
                    "the idempotent reparse request previously failed",
                )
            return self.get(user_id=user_id, task_id=task_id, material_id=material_id)
        return self._parse_and_save(
            material=material,
            user_id=user_id,
            task_id=task_id,
            content=content,
            parse_id=request.parse_id,
        )

    def delete(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        material_id: UUID,
        idempotency_key: str,
    ) -> None:
        self._require_task(user_id=user_id, task_id=task_id)
        deleted = self._materials.delete(
            material_id,
            user_id=user_id,
            task_id=task_id,
            idempotency_key=idempotency_key,
            now=self._clock(),
        )
        if deleted is None:
            raise MaterialNotFound(str(material_id))
        self._commit()

    def _parse_and_save(
        self,
        *,
        material: ResearchMaterial,
        user_id: UUID,
        task_id: UUID,
        content: bytes,
        parse_id: UUID | None = None,
        begin: bool = True,
        commit: bool = True,
        map_unavailable_reason: bool = False,
    ) -> ResearchMaterial:
        parse_id = parse_id or uuid4()
        started_at = self._clock()
        if begin:
            self._materials.begin_reparse(
                material.material_id,
                user_id=user_id,
                task_id=task_id,
                parse_id=parse_id,
                now=started_at,
                expected_current_version=material.current_parse_version,
            )
        version = len(
            self._materials.list_parses(
                material.material_id, user_id=user_id, task_id=task_id
            )
        ) + 1
        try:
            parsed = self._parser(
                filename=material.original_filename,
                media_type=material.media_type,
                content=content,
                material_id=material.material_id,
                parse_id=parse_id,
            )
        except MaterialParseError as error:
            failure_code = (
                self._ingestion_error_code(material, error.code)
                if map_unavailable_reason
                else error.code
            )
            failed = MaterialParseVersion.failed(
                parse_id=parse_id,
                material_id=material.material_id,
                version=version,
                parser_name="qunxue-deterministic-document-parser",
                parser_version="1.0",
                schema_version="1",
                error_code=failure_code,
                now=self._clock(),
            )
            self._materials.save_parse(failed)
            if commit:
                self._commit()
            raise
        parse_version = MaterialParseVersion.create(
            parse_id=parse_id,
            material_id=material.material_id,
            version=version,
            parser_name=parsed.parser_name,
            parser_version=parsed.parser_version,
            schema_version=parsed.schema_version,
            full_text=parsed.full_text,
            structured_document=parsed.structured_document,
            blocks=parsed.blocks,
            content_hash=parsed.content_hash,
            now=self._clock(),
        )
        self._materials.save_parse(parse_version)
        if commit:
            self._commit()
        updated = self._materials.get(
            material.material_id, user_id=user_id, task_id=task_id
        )
        if updated is None:
            raise MaterialNotFound(str(material.material_id))
        return updated

    @staticmethod
    def _ingestion_error_code(material: ResearchMaterial, error_code: str) -> str:
        if material.material_format is MaterialFormat.PDF and error_code in {
            "empty_material",
            "no_extractable_text",
            "pdf_text_extraction_failed",
        }:
            return "ocr_required"
        return error_code

    def _require_task(self, *, user_id: UUID, task_id: UUID) -> None:
        if self._research_tasks.get(task_id, user_id) is None:
            from qunxue_api.modules.research_intake import ResearchTaskNotFound

            raise ResearchTaskNotFound(str(task_id))
