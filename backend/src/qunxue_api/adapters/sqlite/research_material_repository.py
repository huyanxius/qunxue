"""SQLite persistence for task-scoped research materials."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import and_, delete, or_, select, update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from qunxue_api.adapters.sqlite.research_material_model import (
    ResearchMaterialBlobRow,
    ResearchMaterialBlockRow,
    ResearchMaterialIngestionJobRow,
    ResearchMaterialParseVersionRow,
    ResearchMaterialReparseRequestRow,
    ResearchMaterialRow,
)
from qunxue_api.modules.research_materials import (
    MaterialBlock,
    MaterialDeleted,
    MaterialFormat,
    MaterialIdempotencyConflict,
    MaterialIngestionJob,
    MaterialIngestionStatus,
    MaterialKind,
    MaterialParseVersion,
    MaterialReparseRequest,
    MaterialStatus,
    MaterialVersionConflict,
    ResearchMaterial,
)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class SqliteResearchMaterialRepository:
    """Repository with ownership predicates on every content read/write."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        idempotency_key: str,
        filename: str,
        media_type: str | None,
        content: bytes,
        material_kind: MaterialKind = MaterialKind.OTHER,
        display_name: str | None = None,
        processing_policy_version: str = "1",
        now: datetime,
    ) -> ResearchMaterial:
        candidate = ResearchMaterial.create(
            user_id=user_id,
            task_id=task_id,
            idempotency_key=idempotency_key,
            original_filename=filename,
            media_type=media_type,
            content=content,
            material_kind=material_kind,
            display_name=display_name,
            processing_policy_version=processing_policy_version,
            now=now,
        )
        self._session.execute(
            insert(ResearchMaterialRow)
            .values(
                material_id=str(candidate.material_id),
                user_id=str(candidate.user_id),
                task_id=str(candidate.task_id),
                idempotency_key=candidate.idempotency_key,
                delete_idempotency_key=None,
                original_filename=candidate.original_filename,
                display_name=candidate.display_name,
                media_type=candidate.media_type,
                material_format=candidate.material_format.value,
                material_kind=candidate.material_kind.value,
                size_bytes=candidate.size_bytes,
                content_hash=candidate.content_hash,
                status=candidate.status.value,
                current_parse_id=None,
                current_parse_version=None,
                processing_policy_version=candidate.processing_policy_version,
                last_error_code=None,
                created_at=candidate.created_at,
                updated_at=candidate.updated_at,
                deleted_at=None,
            )
            .on_conflict_do_nothing(
                index_elements=["user_id", "task_id", "idempotency_key"]
            )
        )
        winner = self._session.scalar(
            select(ResearchMaterialRow).where(
                ResearchMaterialRow.user_id == str(user_id),
                ResearchMaterialRow.task_id == str(task_id),
                ResearchMaterialRow.idempotency_key == idempotency_key,
            )
        )
        if winner is None:
            raise RuntimeError("research material insert did not return a persisted row")
        if (
            winner.content_hash != candidate.content_hash
            or winner.original_filename != candidate.original_filename
            or winner.media_type != candidate.media_type
            or winner.display_name != candidate.display_name
            or winner.material_kind != candidate.material_kind.value
            or winner.processing_policy_version != candidate.processing_policy_version
        ):
            raise MaterialIdempotencyConflict(
                "idempotency key was already used for different material"
            )
        if winner.material_id == str(candidate.material_id):
            self._session.execute(
                insert(ResearchMaterialBlobRow)
                .values(
                    material_id=str(candidate.material_id),
                    content_hash=candidate.content_hash,
                    size_bytes=candidate.size_bytes,
                    content=content,
                )
                .on_conflict_do_nothing(index_elements=["material_id"])
            )
        return self._to_domain(winner)

    def get(
        self,
        material_id: UUID,
        *,
        user_id: UUID,
        task_id: UUID,
        include_deleted: bool = False,
    ) -> ResearchMaterial | None:
        query = select(ResearchMaterialRow).where(
            ResearchMaterialRow.material_id == str(material_id),
            ResearchMaterialRow.user_id == str(user_id),
            ResearchMaterialRow.task_id == str(task_id),
        )
        if not include_deleted:
            query = query.where(ResearchMaterialRow.status != MaterialStatus.DELETED.value)
        return self._to_domain(self._session.scalar(query))

    def get_owned(self, material_id: UUID, *, user_id: UUID) -> ResearchMaterial | None:
        return self._to_domain(
            self._session.scalar(
                select(ResearchMaterialRow).where(
                    ResearchMaterialRow.material_id == str(material_id),
                    ResearchMaterialRow.user_id == str(user_id),
                    ResearchMaterialRow.status != MaterialStatus.DELETED.value,
                )
            )
        )

    def list_owned(
        self, *, user_id: UUID, limit: int = 100, offset: int = 0
    ) -> tuple[ResearchMaterial, ...]:
        rows = self._session.scalars(
            select(ResearchMaterialRow)
            .where(
                ResearchMaterialRow.user_id == str(user_id),
                ResearchMaterialRow.status != MaterialStatus.DELETED.value,
            )
            .order_by(ResearchMaterialRow.created_at.desc(), ResearchMaterialRow.material_id.desc())
            .limit(limit)
            .offset(offset)
        )
        return tuple(self._to_domain(row) for row in rows)

    def is_external_model_processable(
        self,
        material_id: UUID,
        *,
        user_id: UUID,
        task_id: UUID,
    ) -> bool:
        """Gate external-model use without changing manual material reads.

        A legacy row without a professional profile preserves its established
        behavior. Once cataloged, the archive profile becomes authoritative.
        """

        from qunxue_api.adapters.sqlite.professional_material_repository import (
            SqliteProfessionalMaterialRepository,
        )

        profile = SqliteProfessionalMaterialRepository(self._session).get_profile(
            material_id,
            user_id=user_id,
            task_id=task_id,
        )
        return profile is None or profile.allows_external_model_processing

    def list(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        include_deleted: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[ResearchMaterial, ...]:
        if limit < 1 or limit > 500:
            raise ValueError("limit must be between 1 and 500")
        if offset < 0:
            raise ValueError("offset must be non-negative")
        query = (
            select(ResearchMaterialRow)
            .where(
                ResearchMaterialRow.user_id == str(user_id),
                ResearchMaterialRow.task_id == str(task_id),
            )
            .order_by(ResearchMaterialRow.created_at.desc(), ResearchMaterialRow.material_id.desc())
            .limit(limit)
            .offset(offset)
        )
        if not include_deleted:
            query = query.where(ResearchMaterialRow.status != MaterialStatus.DELETED.value)
        return tuple(self._to_domain(row) for row in self._session.scalars(query))

    def get_original(
        self, material_id: UUID, *, user_id: UUID, task_id: UUID
    ) -> bytes | None:
        owned = self.get(material_id, user_id=user_id, task_id=task_id)
        if owned is None:
            return None
        row = self._session.scalar(
            select(ResearchMaterialBlobRow).where(
                ResearchMaterialBlobRow.material_id == str(material_id)
            )
        )
        return bytes(row.content) if row is not None else None

    def get_parse(
        self,
        material_id: UUID,
        parse_id: UUID,
        *,
        user_id: UUID,
        task_id: UUID,
    ) -> MaterialParseVersion | None:
        if self.get(material_id, user_id=user_id, task_id=task_id) is None:
            return None
        row = self._session.scalar(
            select(ResearchMaterialParseVersionRow).where(
                ResearchMaterialParseVersionRow.material_id == str(material_id),
                ResearchMaterialParseVersionRow.parse_id == str(parse_id),
            )
        )
        return self._to_parse(row)

    def list_parses(
        self, material_id: UUID, *, user_id: UUID, task_id: UUID
    ) -> tuple[MaterialParseVersion, ...]:
        if self.get(material_id, user_id=user_id, task_id=task_id) is None:
            return ()
        rows = self._session.scalars(
            select(ResearchMaterialParseVersionRow)
            .where(ResearchMaterialParseVersionRow.material_id == str(material_id))
            .order_by(ResearchMaterialParseVersionRow.version.desc())
        )
        return tuple(parsed for row in rows if (parsed := self._to_parse(row)) is not None)

    def get_segment(
        self,
        material_id: UUID,
        parse_id: UUID,
        segment_id: str,
        *,
        user_id: UUID,
        task_id: UUID,
    ) -> MaterialBlock | None:
        if self.get(material_id, user_id=user_id, task_id=task_id) is None:
            return None
        row = self._session.scalar(
            select(ResearchMaterialBlockRow).where(
                ResearchMaterialBlockRow.material_id == str(material_id),
                ResearchMaterialBlockRow.parse_id == str(parse_id),
                ResearchMaterialBlockRow.segment_id == segment_id,
            )
        )
        return self._to_block(row)

    def begin_reparse(
        self,
        material_id: UUID,
        *,
        user_id: UUID,
        task_id: UUID,
        parse_id: UUID,
        now: datetime,
        expected_current_version: int | None = None,
    ) -> ResearchMaterial | None:
        material = self.get(material_id, user_id=user_id, task_id=task_id)
        if material is None:
            return None
        if material.status is MaterialStatus.DELETED:
            raise MaterialDeleted("deleted material cannot be reparsed")
        if (
            expected_current_version is not None
            and material.current_parse_version != expected_current_version
        ):
            raise MaterialVersionConflict("material changed before reparse started")
        updated = material.begin_reparse(parse_id=parse_id, now=now)
        result = self._session.execute(
            update(ResearchMaterialRow)
            .where(
                ResearchMaterialRow.material_id == str(material_id),
                ResearchMaterialRow.user_id == str(user_id),
                ResearchMaterialRow.task_id == str(task_id),
                ResearchMaterialRow.status == material.status.value,
                ResearchMaterialRow.current_parse_version
                == material.current_parse_version,
            )
            .values(
                status=updated.status.value,
                updated_at=updated.updated_at,
                last_error_code=None,
            )
        )
        if result.rowcount != 1:
            raise MaterialVersionConflict("material changed before reparse started")
        return updated

    def reserve_reparse(
        self,
        material_id: UUID,
        *,
        user_id: UUID,
        task_id: UUID,
        idempotency_key: str,
        parse_id: UUID,
        now: datetime,
    ) -> MaterialReparseRequest:
        """Atomically bind a retry key to one material and immutable parse ID."""

        normalized_key = idempotency_key.strip()
        if not normalized_key:
            raise ValueError("idempotency_key is required")
        self._session.execute(
            insert(ResearchMaterialReparseRequestRow)
            .values(
                user_id=str(user_id),
                task_id=str(task_id),
                idempotency_key=normalized_key,
                material_id=str(material_id),
                parse_id=str(parse_id),
                created_at=now,
            )
            .on_conflict_do_nothing(
                index_elements=["user_id", "task_id", "idempotency_key"]
            )
        )
        winner = self._session.scalar(
            select(ResearchMaterialReparseRequestRow).where(
                ResearchMaterialReparseRequestRow.user_id == str(user_id),
                ResearchMaterialReparseRequestRow.task_id == str(task_id),
                ResearchMaterialReparseRequestRow.idempotency_key == normalized_key,
            )
        )
        if winner is None:
            raise RuntimeError("reparse request reservation was not persisted")
        if winner.material_id != str(material_id):
            raise MaterialIdempotencyConflict(
                "idempotency key was already used to reparse another material"
            )
        return MaterialReparseRequest(
            material_id=UUID(winner.material_id),
            parse_id=UUID(winner.parse_id),
            idempotency_key=winner.idempotency_key,
            created_at=_utc(winner.created_at),
        )

    def save_parse(self, parsed: MaterialParseVersion) -> MaterialParseVersion:
        material_row = self._session.scalar(
            select(ResearchMaterialRow).where(
                ResearchMaterialRow.material_id == str(parsed.material_id)
            )
        )
        if material_row is None:
            raise MaterialVersionConflict("material does not exist")
        material = self._to_domain(material_row)
        if material.status is MaterialStatus.DELETED:
            raise MaterialDeleted("deleted material cannot accept a parse")
        existing = self._session.scalar(
            select(ResearchMaterialParseVersionRow).where(
                ResearchMaterialParseVersionRow.material_id == str(parsed.material_id),
                ResearchMaterialParseVersionRow.version == parsed.version,
            )
        )
        if existing is not None:
            persisted = self._to_parse(existing)
            if persisted == parsed:
                return parsed
            raise MaterialVersionConflict("parse version already contains different content")

        latest_version = self._session.scalar(
            select(ResearchMaterialParseVersionRow.version)
            .where(ResearchMaterialParseVersionRow.material_id == str(parsed.material_id))
            .order_by(ResearchMaterialParseVersionRow.version.desc())
            .limit(1)
        )
        expected = int(latest_version or 0) + 1
        if parsed.version != expected:
            raise MaterialVersionConflict(
                f"expected parse version {expected}, got {parsed.version}"
            )
        if parsed.status is MaterialStatus.READY:
            updated = material.record_parse_success(parsed)
        elif parsed.status is MaterialStatus.FAILED:
            updated = material.fail_parse(
                parse_id=parsed.parse_id,
                error_code=parsed.error_code or "parse_failed",
                now=parsed.completed_at or parsed.created_at,
            )
        else:
            raise MaterialVersionConflict("parse status must be ready or failed")

        self._session.add(
            ResearchMaterialParseVersionRow(
                parse_id=str(parsed.parse_id),
                material_id=str(parsed.material_id),
                version=parsed.version,
                parser_name=parsed.parser_name,
                parser_version=parsed.parser_version,
                schema_version=parsed.schema_version,
                status=parsed.status.value,
                full_text=parsed.full_text,
                structured_document=parsed.structured_document,
                content_hash=parsed.content_hash,
                error_code=parsed.error_code,
                created_at=parsed.created_at,
                completed_at=parsed.completed_at,
            )
        )
        # As with the raw BLOB, source blocks have no ORM relationship to the
        # immutable parse row. Persist the parent before its FK-bound blocks.
        self._session.flush()
        for block in parsed.blocks:
            self._session.add(
                ResearchMaterialBlockRow(
                    parse_id=str(block.parse_id),
                    segment_id=block.segment_id,
                    material_id=str(block.material_id),
                    ordinal=block.ordinal,
                    kind=block.kind,
                    text=block.text,
                    content_hash=block.content_hash,
                    locator=block.locator.as_dict(),
                )
            )
        self._session.execute(
            update(ResearchMaterialRow)
            .where(ResearchMaterialRow.material_id == str(parsed.material_id))
            .values(
                status=updated.status.value,
                current_parse_id=(
                    str(updated.current_parse_id) if updated.current_parse_id is not None else None
                ),
                current_parse_version=updated.current_parse_version,
                updated_at=updated.updated_at,
                last_error_code=updated.last_error_code,
            )
        )
        return parsed

    def enqueue_ingestion(
        self,
        *,
        material: ResearchMaterial,
        parse_id: UUID,
        now: datetime,
        max_attempts: int = 3,
    ) -> MaterialIngestionJob:
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        job_id = uuid4()
        self._session.execute(
            insert(ResearchMaterialIngestionJobRow)
            .values(
                job_id=str(job_id),
                material_id=str(material.material_id),
                user_id=str(material.user_id),
                task_id=str(material.task_id),
                parse_id=str(parse_id),
                ingestion_status=MaterialIngestionStatus.QUEUED.value,
                attempt_count=0,
                max_attempts=max_attempts,
                available_at=now,
                lease_expires_at=None,
                error_code=None,
                created_at=now,
                updated_at=now,
                completed_at=None,
            )
            .on_conflict_do_nothing(index_elements=["material_id", "parse_id"])
        )
        row = self._session.scalar(
            select(ResearchMaterialIngestionJobRow).where(
                ResearchMaterialIngestionJobRow.material_id == str(material.material_id),
                ResearchMaterialIngestionJobRow.parse_id == str(parse_id),
            )
        )
        if row is None:
            raise RuntimeError("material ingestion job was not persisted")
        return self._to_ingestion(row)

    def get_ingestion(self, job_id: UUID) -> MaterialIngestionJob | None:
        return self._to_ingestion(
            self._session.scalar(
                select(ResearchMaterialIngestionJobRow).where(
                    ResearchMaterialIngestionJobRow.job_id == str(job_id)
                )
            )
        )

    def get_material_ingestion(
        self, material_id: UUID, *, user_id: UUID, task_id: UUID
    ) -> MaterialIngestionJob | None:
        row = self._session.scalar(
            select(ResearchMaterialIngestionJobRow)
            .where(
                ResearchMaterialIngestionJobRow.material_id == str(material_id),
                ResearchMaterialIngestionJobRow.user_id == str(user_id),
                ResearchMaterialIngestionJobRow.task_id == str(task_id),
            )
            .order_by(ResearchMaterialIngestionJobRow.created_at.desc())
            .limit(1)
        )
        return self._to_ingestion(row)

    def claim_ingestion(
        self, job_id: UUID, *, now: datetime, lease_expires_at: datetime
    ) -> MaterialIngestionJob | None:
        row = self._session.scalar(
            select(ResearchMaterialIngestionJobRow).where(
                ResearchMaterialIngestionJobRow.job_id == str(job_id)
            )
        )
        if row is None or row.attempt_count >= row.max_attempts:
            return None
        status = MaterialIngestionStatus(row.ingestion_status)
        available = _utc(row.available_at) <= _utc(now)
        stale = (
            row.lease_expires_at is not None
            and _utc(row.lease_expires_at) <= _utc(now)
        )
        queued_or_failed = status is MaterialIngestionStatus.QUEUED or (
            status is MaterialIngestionStatus.FAILED and row.completed_at is None
        )
        if not (
            (queued_or_failed and available)
            or (status is MaterialIngestionStatus.PROCESSING and stale)
        ):
            return None
        next_parse_id = str(uuid4()) if row.attempt_count else row.parse_id
        result = self._session.execute(
            update(ResearchMaterialIngestionJobRow)
            .where(
                ResearchMaterialIngestionJobRow.job_id == str(job_id),
                ResearchMaterialIngestionJobRow.ingestion_status == status.value,
                ResearchMaterialIngestionJobRow.attempt_count == row.attempt_count,
            )
            .values(
                ingestion_status=MaterialIngestionStatus.PROCESSING.value,
                attempt_count=row.attempt_count + 1,
                parse_id=next_parse_id,
                lease_expires_at=lease_expires_at,
                error_code=None,
                updated_at=now,
                completed_at=None,
            )
        )
        if result.rowcount != 1:
            return None
        return self.get_ingestion(job_id)

    def complete_ingestion(
        self,
        job_id: UUID,
        *,
        expected_attempt_count: int,
        expected_parse_id: UUID,
        now: datetime,
    ) -> MaterialIngestionJob | None:
        result = self._session.execute(
            update(ResearchMaterialIngestionJobRow)
            .where(
                ResearchMaterialIngestionJobRow.job_id == str(job_id),
                ResearchMaterialIngestionJobRow.ingestion_status
                == MaterialIngestionStatus.PROCESSING.value,
                ResearchMaterialIngestionJobRow.attempt_count == expected_attempt_count,
                ResearchMaterialIngestionJobRow.parse_id == str(expected_parse_id),
            )
            .values(
                ingestion_status=MaterialIngestionStatus.READY.value,
                lease_expires_at=None,
                error_code=None,
                updated_at=now,
                completed_at=now,
            )
        )
        if result.rowcount != 1:
            return None
        job = self.get_ingestion(job_id)
        if job is None:
            raise RuntimeError("completed ingestion job disappeared")
        return job

    def fail_ingestion(
        self,
        job_id: UUID,
        *,
        expected_attempt_count: int,
        expected_parse_id: UUID,
        error_code: str,
        retry_at: datetime | None,
        now: datetime,
    ) -> MaterialIngestionJob | None:
        result = self._session.execute(
            update(ResearchMaterialIngestionJobRow)
            .where(
                ResearchMaterialIngestionJobRow.job_id == str(job_id),
                ResearchMaterialIngestionJobRow.ingestion_status
                == MaterialIngestionStatus.PROCESSING.value,
                ResearchMaterialIngestionJobRow.attempt_count == expected_attempt_count,
                ResearchMaterialIngestionJobRow.parse_id == str(expected_parse_id),
            )
            .values(
                ingestion_status=MaterialIngestionStatus.FAILED.value,
                available_at=retry_at or now,
                lease_expires_at=None,
                error_code=error_code,
                updated_at=now,
                completed_at=None if retry_at is not None else now,
            )
        )
        if result.rowcount != 1:
            return None
        job = self.get_ingestion(job_id)
        if job is None:
            raise RuntimeError("failed ingestion job disappeared")
        return job

    def recoverable_ingestion_ids(self, *, now: datetime) -> tuple[UUID, ...]:
        rows = self._session.scalars(
            select(ResearchMaterialIngestionJobRow)
            .where(
                ResearchMaterialIngestionJobRow.attempt_count
                < ResearchMaterialIngestionJobRow.max_attempts,
                or_(
                    and_(
                        ResearchMaterialIngestionJobRow.ingestion_status
                        == MaterialIngestionStatus.QUEUED.value,
                        ResearchMaterialIngestionJobRow.available_at <= now,
                    ),
                    and_(
                        ResearchMaterialIngestionJobRow.ingestion_status
                        == MaterialIngestionStatus.FAILED.value,
                        ResearchMaterialIngestionJobRow.completed_at.is_(None),
                    ),
                    and_(
                        ResearchMaterialIngestionJobRow.ingestion_status
                        == MaterialIngestionStatus.PROCESSING.value,
                        ResearchMaterialIngestionJobRow.lease_expires_at <= now,
                    ),
                ),
            )
            .order_by(ResearchMaterialIngestionJobRow.created_at)
        )
        return tuple(UUID(row.job_id) for row in rows)

    def delete(
        self,
        material_id: UUID,
        *,
        user_id: UUID,
        task_id: UUID,
        idempotency_key: str,
        now: datetime,
    ) -> ResearchMaterial | None:
        replay = self._session.scalar(
            select(ResearchMaterialRow).where(
                ResearchMaterialRow.user_id == str(user_id),
                ResearchMaterialRow.task_id == str(task_id),
                ResearchMaterialRow.delete_idempotency_key == idempotency_key,
            )
        )
        if replay is not None:
            if replay.material_id != str(material_id):
                raise MaterialIdempotencyConflict(
                    "idempotency key was already used to delete another material"
                )
            return self._to_domain(replay)
        row = self._session.scalar(
            select(ResearchMaterialRow).where(
                ResearchMaterialRow.material_id == str(material_id),
                ResearchMaterialRow.user_id == str(user_id),
                ResearchMaterialRow.task_id == str(task_id),
            )
        )
        if row is None or row.status == MaterialStatus.DELETED.value:
            return None
        material = self._to_domain(row)
        assert material is not None
        deleted = material.delete(now=now)
        try:
            self._session.execute(
                update(ResearchMaterialRow)
                .where(
                    ResearchMaterialRow.material_id == str(material_id),
                    ResearchMaterialRow.user_id == str(user_id),
                    ResearchMaterialRow.task_id == str(task_id),
                    ResearchMaterialRow.status != MaterialStatus.DELETED.value,
                    ResearchMaterialRow.delete_idempotency_key.is_(None),
                )
                .values(
                    status=deleted.status.value,
                    current_parse_id=None,
                    current_parse_version=None,
                    updated_at=deleted.updated_at,
                    deleted_at=deleted.deleted_at,
                    last_error_code=None,
                    delete_idempotency_key=idempotency_key,
                )
            )
        except IntegrityError as error:
            self._session.rollback()
            raise MaterialIdempotencyConflict(
                "idempotency key was already used to delete another material"
            ) from error
        # Explicit deletes make the immediate invalidation guarantee clear
        # even on SQLite connections where FK pragma was not enabled.
        self._session.execute(
            delete(ResearchMaterialBlockRow).where(
                ResearchMaterialBlockRow.material_id == str(material_id)
            )
        )
        self._session.execute(
            delete(ResearchMaterialParseVersionRow).where(
                ResearchMaterialParseVersionRow.material_id == str(material_id)
            )
        )
        self._session.execute(
            delete(ResearchMaterialBlobRow).where(
                ResearchMaterialBlobRow.material_id == str(material_id)
            )
        )
        return deleted

    @staticmethod
    def _to_ingestion(
        row: ResearchMaterialIngestionJobRow | None,
    ) -> MaterialIngestionJob | None:
        if row is None:
            return None
        return MaterialIngestionJob(
            job_id=UUID(row.job_id),
            material_id=UUID(row.material_id),
            user_id=UUID(row.user_id),
            task_id=UUID(row.task_id),
            parse_id=UUID(row.parse_id),
            ingestion_status=MaterialIngestionStatus(row.ingestion_status),
            attempt_count=row.attempt_count,
            max_attempts=row.max_attempts,
            available_at=_utc(row.available_at),
            lease_expires_at=_utc(row.lease_expires_at) if row.lease_expires_at else None,
            error_code=row.error_code,
            created_at=_utc(row.created_at),
            updated_at=_utc(row.updated_at),
            completed_at=_utc(row.completed_at) if row.completed_at else None,
        )

    @staticmethod
    def _to_domain(row: ResearchMaterialRow | None) -> ResearchMaterial | None:
        if row is None:
            return None
        return ResearchMaterial(
            material_id=UUID(row.material_id),
            user_id=UUID(row.user_id),
            task_id=UUID(row.task_id),
            idempotency_key=row.idempotency_key,
            original_filename=row.original_filename,
            display_name=row.display_name,
            media_type=row.media_type,
            material_format=MaterialFormat(row.material_format),
            material_kind=MaterialKind(row.material_kind),
            size_bytes=row.size_bytes,
            content_hash=row.content_hash,
            status=MaterialStatus(row.status),
            current_parse_id=UUID(row.current_parse_id) if row.current_parse_id else None,
            current_parse_version=row.current_parse_version,
            processing_policy_version=row.processing_policy_version,
            created_at=_utc(row.created_at),
            updated_at=_utc(row.updated_at),
            deleted_at=_utc(row.deleted_at) if row.deleted_at else None,
            last_error_code=row.last_error_code,
        )

    def _to_parse(self, row: ResearchMaterialParseVersionRow | None) -> MaterialParseVersion | None:
        if row is None:
            return None
        blocks = tuple(
            block
            for block_row in self._session.scalars(
                select(ResearchMaterialBlockRow)
                .where(ResearchMaterialBlockRow.parse_id == row.parse_id)
                .order_by(ResearchMaterialBlockRow.ordinal)
            )
            if (block := self._to_block(block_row)) is not None
        )
        return MaterialParseVersion(
            parse_id=UUID(row.parse_id),
            material_id=UUID(row.material_id),
            version=row.version,
            parser_name=row.parser_name,
            parser_version=row.parser_version,
            schema_version=row.schema_version,
            status=MaterialStatus(row.status),
            full_text=row.full_text,
            structured_document=dict(row.structured_document or {}),
            blocks=blocks,
            content_hash=row.content_hash,
            created_at=_utc(row.created_at),
            completed_at=_utc(row.completed_at) if row.completed_at else None,
            error_code=row.error_code,
        )

    @staticmethod
    def _to_block(row: ResearchMaterialBlockRow | None) -> MaterialBlock | None:
        if row is None:
            return None
        from qunxue_api.modules.research_materials import MaterialLocator

        return MaterialBlock(
            segment_id=row.segment_id,
            parse_id=UUID(row.parse_id),
            material_id=UUID(row.material_id),
            ordinal=row.ordinal,
            kind=row.kind,
            text=row.text,
            content_hash=row.content_hash,
            locator=MaterialLocator.from_dict(row.locator),
        )
