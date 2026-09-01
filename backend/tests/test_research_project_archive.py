from __future__ import annotations

import hashlib
import json
from io import BytesIO
from uuid import UUID
from zipfile import ZipFile

from qunxue_api.modules.research_exchange import (
    ArchiveArtifact,
    ExchangeLoss,
    ExchangeReport,
    QdpxProject,
    build_research_project_archive,
    export_qdpx,
    open_research_project_archive,
    validate_qdpx,
)


def _archive() -> bytes:
    project = QdpxProject(
        project_id=UUID("40000000-0000-4000-8000-000000000001"),
        name="社区菜市场摊贩互助研究",
        origin="群学致知",
        description="从摊贩日常协作观察地方互助网络。",
    )
    qdpx = export_qdpx(project)
    report = ExchangeReport(
        losses=(
            ExchangeLoss(
                object_type="research_document",
                object_id="document-1",
                field="formatting",
                reason="QDPX does not represent document formatting profiles",
                disposition="recovery_manifest",
            ),
        )
    )
    return build_research_project_archive(
        archive_id=UUID("40000000-0000-4000-8000-000000000002"),
        task_id=UUID("40000000-0000-4000-8000-000000000001"),
        qdpx=qdpx.payload,
        recovery_manifest={
            "schema_version": "qunxue-research-project-archive-v1",
            "task": {"task_id": "40000000-0000-4000-8000-000000000001", "version": 7},
        },
        exchange_report=report,
        audit_events=(
            {
                "event_id": "event-1",
                "event_type": "document.version_created",
                "object_id": "document-1",
                "object_version": "4",
            },
        ),
        artifacts=(
            ArchiveArtifact(
                path="documents/formal-draft-v4.md",
                media_type="text/markdown",
                content="# 正式文稿\n\n可核验的研究结论。\n".encode(),
            ),
            ArchiveArtifact(
                path="documents/formal-draft-v4.json",
                media_type="application/json",
                content=b'{"document_id":"document-1","version":4}',
            ),
        ),
    ).payload


def test_bagit_archive_is_deterministic_self_checking_and_contains_open_outputs() -> None:
    first = _archive()
    second = _archive()

    assert first == second
    with ZipFile(BytesIO(first)) as archive:
        names = set(archive.namelist())
        assert {
            "bagit.txt",
            "bag-info.txt",
            "manifest-sha256.txt",
            "tagmanifest-sha256.txt",
            "data/exchange/project.qdpx",
            "data/project.json",
            "data/reports/exchange-loss.json",
            "data/reports/exchange-loss.md",
            "data/audit/events.ndjson",
            "data/documents/formal-draft-v4.md",
            "data/documents/formal-draft-v4.json",
        } <= names
        manifest_lines = archive.read("manifest-sha256.txt").decode().splitlines()
        for line in manifest_lines:
            digest, path = line.split("  ", 1)
            assert hashlib.sha256(archive.read(path)).hexdigest() == digest

    opened = open_research_project_archive(first)
    assert opened.valid is True
    assert validate_qdpx(opened.qdpx).valid is True
    assert opened.recovery_manifest["task"]["version"] == 7
    assert opened.exchange_report.losses[0].field == "formatting"
    assert opened.audit_events[0]["object_version"] == "4"


def test_archive_reader_rejects_payload_changed_after_manifest_creation() -> None:
    payload = _archive()
    rewritten = BytesIO()
    with ZipFile(BytesIO(payload)) as source, ZipFile(rewritten, "w") as target:
        for item in source.infolist():
            content = source.read(item)
            if item.filename == "data/project.json":
                value = json.loads(content)
                value["task"]["version"] = 999
                content = json.dumps(value).encode()
            target.writestr(item, content)

    opened = open_research_project_archive(rewritten.getvalue())

    assert opened.valid is False
    assert "data/project.json" in opened.errors[0]
