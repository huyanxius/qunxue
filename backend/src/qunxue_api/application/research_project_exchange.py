"""Compose published research contracts into auditable project exchange artifacts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from enum import Enum
from typing import Protocol
from uuid import UUID

from qunxue_api.modules.research_analysis import (
    AnalysisAnnotation,
    AnalysisCode,
    AnalysisMemo,
    CodebookEntry,
)
from qunxue_api.modules.research_cycle import ResearchCycleSnapshot
from qunxue_api.modules.research_exchange import (
    ArchiveArtifact,
    AuditActorType,
    ExchangeReport,
    QdpxProject,
    ResearchAuditEvent,
    ResearchAuditEventType,
    ResearchExchangeDirection,
    ResearchExchangeRun,
    ResearchProjectArchive,
    ResearchProjectAuditRepository,
    build_research_project_archive,
    export_qdpx,
    import_qdpx,
    validate_qdpx,
)
from qunxue_api.modules.research_framework import (
    ResearchDocumentService,
    ResearchDocumentSnapshot,
    ResearchDocumentStatus,
)
from qunxue_api.modules.research_intake import (
    ResearchTask,
    ResearchTaskNotFound,
    ResearchTaskRepository,
)
from qunxue_api.modules.research_materials import (
    MaterialParseVersion,
    ProfessionalMaterialArchive,
    ResearchMaterial,
)


class ResearchProjectMaterialReader(Protocol):
    def list(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        include_deleted: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[ResearchMaterial, ...]: ...

    def list_parses(
        self, material_id: UUID, *, user_id: UUID, task_id: UUID
    ) -> tuple[MaterialParseVersion, ...]: ...

    def get_original(
        self, material_id: UUID, *, user_id: UUID, task_id: UUID
    ) -> bytes | None: ...


class ResearchProjectProfessionalArchiveReader(Protocol):
    def snapshot(self, *, user_id: UUID, task_id: UUID) -> ProfessionalMaterialArchive: ...


class ResearchProjectAnalysisReader(Protocol):
    def list_annotations(
        self, *, user_id: UUID, task_id: UUID
    ) -> tuple[AnalysisAnnotation, ...]: ...

    def list_codes(self, *, user_id: UUID, task_id: UUID) -> tuple[AnalysisCode, ...]: ...

    def list_memos(self, *, user_id: UUID, task_id: UUID) -> tuple[AnalysisMemo, ...]: ...

    def list_codebook_entries(
        self, *, user_id: UUID, task_id: UUID
    ) -> tuple[CodebookEntry, ...]: ...


class ResearchProjectDocumentReader(Protocol):
    def list_for_task(self, task_id: UUID) -> tuple[ResearchDocumentSnapshot, ...]: ...


class ResearchProjectCycleReader(Protocol):
    def list_versions(self, task_id: UUID) -> tuple[ResearchCycleSnapshot, ...]: ...


class ResearchProjectMapping(Protocol):
    project: QdpxProject
    report: ExchangeReport
    recovery_manifest: dict[str, object]


class ResearchProjectMapper(Protocol):
    def __call__(
        self,
        *,
        task: ResearchTask,
        materials: tuple[ResearchMaterial, ...],
        parses: tuple[MaterialParseVersion, ...],
        archive: ProfessionalMaterialArchive,
        annotations: tuple[AnalysisAnnotation, ...],
        codes: tuple[AnalysisCode, ...],
        memos: tuple[AnalysisMemo, ...],
        codebook_entries: tuple[CodebookEntry, ...],
        original_contents: dict[UUID, bytes],
        extension_snapshots: dict[str, object],
    ) -> ResearchProjectMapping: ...


class ResearchExchangeIdempotencyConflict(RuntimeError):
    """The caller reused an exchange key whose artifact is no longer in memory."""


@dataclass(frozen=True, slots=True)
class ResearchProjectArchiveExport:
    exchange: ResearchExchangeRun
    archive: ResearchProjectArchive
    report: ExchangeReport


@dataclass(frozen=True, slots=True)
class ResearchProjectImportPreview:
    exchange: ResearchExchangeRun
    project: QdpxProject
    report: ExchangeReport
    restored: bool = False


def _jsonable(value: object) -> object:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return value


def _domain_payload(value: object) -> dict[str, object]:
    rendered = _jsonable(asdict(value))
    assert isinstance(rendered, dict)
    return rendered


def _report_payload(report: ExchangeReport) -> dict[str, object]:
    return {
        "format": report.format,
        "specification_version": report.specification_version,
        "validation_scope": report.validation_scope,
        "losses": [_domain_payload(loss) for loss in report.losses],
        "identities": [_domain_payload(identity) for identity in report.identities],
    }


def _event_payload(event: ResearchAuditEvent) -> dict[str, object]:
    return _domain_payload(event)


class ResearchProjectExchangeApplication:
    """Build exchange snapshots without changing facts owned by research modules."""

    def __init__(
        self,
        *,
        research_tasks: ResearchTaskRepository,
        materials: ResearchProjectMaterialReader,
        professional_archive: ResearchProjectProfessionalArchiveReader,
        analysis: ResearchProjectAnalysisReader,
        documents: ResearchProjectDocumentReader,
        cycles: ResearchProjectCycleReader,
        audit: ResearchProjectAuditRepository,
        project_mapper: ResearchProjectMapper,
        commit: Callable[[], None] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._research_tasks = research_tasks
        self._materials = materials
        self._professional_archive = professional_archive
        self._analysis = analysis
        self._documents = documents
        self._cycles = cycles
        self._audit = audit
        self._project_mapper = project_mapper
        self._commit = commit or (lambda: None)
        self._clock = clock or (lambda: datetime.now(UTC))

    def export_archive(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        idempotency_key: str,
    ) -> ResearchProjectArchiveExport:
        task = self._require_task(user_id=user_id, task_id=task_id)
        self._require_new_exchange_key(
            user_id=user_id,
            task_id=task_id,
            direction=ResearchExchangeDirection.EXPORT,
            idempotency_key=idempotency_key,
        )
        now = self._clock()
        exchange = ResearchExchangeRun.start(
            user_id=user_id,
            task_id=task_id,
            direction=ResearchExchangeDirection.EXPORT,
            format="Qunxue Research Project Archive",
            format_version="1",
            idempotency_key=idempotency_key,
            now=now,
        )
        self._audit.save_exchange(exchange)
        try:
            mapping, document_artifacts = self._map_project(task)
            qdpx = export_qdpx(mapping.project)
            report = ExchangeReport(
                format=mapping.report.format,
                specification_version=mapping.report.specification_version,
                validation_scope=mapping.report.validation_scope,
                losses=tuple((*mapping.report.losses, *qdpx.report.losses)),
                identities=mapping.report.identities,
            )
            report_payload = _report_payload(report)
            event = ResearchAuditEvent.create(
                user_id=user_id,
                task_id=task_id,
                event_type=ResearchAuditEventType.PROJECT_EXPORTED,
                object_type="research_task",
                object_id=str(task_id),
                object_version=str(task.version),
                actor_type=AuditActorType.USER,
                actor_id=str(user_id),
                payload={
                    "exchange_id": str(exchange.exchange_id),
                    "format": "Qunxue Research Project Archive 1",
                    "qdpx_specification_version": "1.0",
                    "loss_count": len(report.losses),
                    "blocking_loss_count": sum(
                        loss.severity.value == "blocking" for loss in report.losses
                    ),
                },
                occurred_at=now,
            )
            prior_events = self._audit.list_events(user_id=user_id, task_id=task_id)
            archive = build_research_project_archive(
                archive_id=exchange.exchange_id,
                task_id=task_id,
                qdpx=qdpx.payload,
                recovery_manifest=mapping.recovery_manifest,
                exchange_report=report,
                audit_events=tuple(_event_payload(item) for item in (*prior_events, event)),
                artifacts=document_artifacts,
            )
            exchange = exchange.complete(
                artifact_sha256=archive.sha256,
                loss_report=report_payload,
                now=self._clock(),
            )
            self._audit.save_exchange(exchange)
            self._audit.append_event(event)
            self._commit()
            return ResearchProjectArchiveExport(
                exchange=exchange,
                archive=archive,
                report=report,
            )
        except Exception:
            self._audit.save_exchange(
                exchange.fail(error_code="archive_export_failed", now=self._clock())
            )
            self._commit()
            raise

    def preview_qdpx_import(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        idempotency_key: str,
        payload: bytes,
    ) -> ResearchProjectImportPreview:
        task = self._require_task(user_id=user_id, task_id=task_id)
        self._require_new_exchange_key(
            user_id=user_id,
            task_id=task_id,
            direction=ResearchExchangeDirection.IMPORT,
            idempotency_key=idempotency_key,
        )
        now = self._clock()
        exchange = ResearchExchangeRun.start(
            user_id=user_id,
            task_id=task_id,
            direction=ResearchExchangeDirection.IMPORT,
            format="REFI-QDA Project",
            format_version="1.0",
            idempotency_key=idempotency_key,
            now=now,
        )
        self._audit.save_exchange(exchange)
        validation = validate_qdpx(payload)
        if not validation.valid:
            self._audit.save_exchange(
                exchange.fail(error_code="qdpx_validation_failed", now=self._clock())
            )
            self._commit()
            raise ValueError("; ".join(validation.errors))
        imported = import_qdpx(payload)
        report = ExchangeReport(validation_scope="official-xsd")
        exchange = exchange.complete(
            artifact_sha256=hashlib.sha256(payload).hexdigest(),
            loss_report=_report_payload(report),
            now=self._clock(),
        )
        event = ResearchAuditEvent.create(
            user_id=user_id,
            task_id=task_id,
            event_type=ResearchAuditEventType.PROJECT_IMPORT_PREVIEWED,
            object_type="research_task",
            object_id=str(task_id),
            object_version=str(task.version),
            actor_type=AuditActorType.USER,
            actor_id=str(user_id),
            payload={
                "exchange_id": str(exchange.exchange_id),
                "source_project_name": imported.project.name,
                "restored": False,
            },
            occurred_at=now,
        )
        self._audit.save_exchange(exchange)
        self._audit.append_event(event)
        self._commit()
        return ResearchProjectImportPreview(
            exchange=exchange,
            project=imported.project,
            report=report,
        )

    def list_audit_events(
        self, *, user_id: UUID, task_id: UUID
    ) -> tuple[ResearchAuditEvent, ...]:
        self._require_task(user_id=user_id, task_id=task_id)
        return self._audit.list_events(user_id=user_id, task_id=task_id)

    def _map_project(
        self, task: ResearchTask
    ) -> tuple[ResearchProjectMapping, tuple[ArchiveArtifact, ...]]:
        materials = self._materials.list(
            user_id=task.user_id,
            task_id=task.task_id,
            include_deleted=True,
            limit=500,
        )
        parses = tuple(
            parse
            for material in materials
            for parse in self._materials.list_parses(
                material.material_id,
                user_id=task.user_id,
                task_id=task.task_id,
            )
        )
        originals = {
            material.material_id: content
            for material in materials
            if (
                content := self._materials.get_original(
                    material.material_id,
                    user_id=task.user_id,
                    task_id=task.task_id,
                )
            )
            is not None
        }
        documents = self._documents.list_for_task(task.task_id)
        document_payloads = [_domain_payload(document) for document in documents]
        cycle_payloads = [
            _domain_payload(snapshot)
            for snapshot in self._cycles.list_versions(task.task_id)
        ]
        return (
            self._project_mapper(
                task=task,
                materials=materials,
                parses=parses,
                archive=self._professional_archive.snapshot(
                    user_id=task.user_id,
                    task_id=task.task_id,
                ),
                annotations=self._analysis.list_annotations(
                    user_id=task.user_id,
                    task_id=task.task_id,
                ),
                codes=self._analysis.list_codes(user_id=task.user_id, task_id=task.task_id),
                memos=self._analysis.list_memos(user_id=task.user_id, task_id=task.task_id),
                codebook_entries=self._analysis.list_codebook_entries(
                    user_id=task.user_id,
                    task_id=task.task_id,
                ),
                original_contents=originals,
                extension_snapshots={
                    "research_cycle_versions": cycle_payloads,
                    "research_documents": document_payloads,
                },
            ),
            (
                *self._material_artifacts(materials, originals),
                *self._document_artifacts(documents),
            ),
        )

    @staticmethod
    def _material_artifacts(
        materials: tuple[ResearchMaterial, ...],
        originals: dict[UUID, bytes],
    ) -> tuple[ArchiveArtifact, ...]:
        return tuple(
            ArchiveArtifact(
                path=f"materials/{material.material_id}/original",
                media_type=material.media_type,
                content=originals[material.material_id],
            )
            for material in materials
            if material.material_id in originals
        )

    def _document_artifacts(
        self, documents: tuple[ResearchDocumentSnapshot, ...]
    ) -> tuple[ArchiveArtifact, ...]:
        service = ResearchDocumentService(repository=self._documents)
        artifacts: list[ArchiveArtifact] = []
        for document in documents:
            stem = f"documents/{document.document_id}/v{document.version}"
            artifacts.append(
                ArchiveArtifact(
                    path=f"{stem}.json",
                    media_type="application/json",
                    content=(
                        json.dumps(
                            _domain_payload(document),
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        )
                        + "\n"
                    ).encode(),
                )
            )
            if document.status is ResearchDocumentStatus.CONFIRMED:
                exported = service.export_markdown(
                    document_id=document.document_id,
                    version=document.version,
                )
                artifacts.append(
                    ArchiveArtifact(
                        path=f"{stem}.md",
                        media_type="text/markdown",
                        content=exported.markdown.encode(),
                    )
                )
        return tuple(artifacts)

    def _require_task(self, *, user_id: UUID, task_id: UUID) -> ResearchTask:
        task = self._research_tasks.get(task_id, user_id)
        if task is None:
            raise ResearchTaskNotFound(task_id)
        return task

    def _require_new_exchange_key(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        direction: ResearchExchangeDirection,
        idempotency_key: str,
    ) -> None:
        existing = self._audit.get_exchange_by_idempotency(
            user_id=user_id,
            task_id=task_id,
            direction=direction,
            idempotency_key=idempotency_key,
        )
        if existing is not None:
            raise ResearchExchangeIdempotencyConflict(
                "exchange request key was already used; use the recorded exchange ID"
            )


__all__ = [
    "ResearchExchangeIdempotencyConflict",
    "ResearchProjectArchiveExport",
    "ResearchProjectExchangeApplication",
    "ResearchProjectImportPreview",
]
