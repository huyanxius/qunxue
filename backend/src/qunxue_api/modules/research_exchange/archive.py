"""BagIt 1.0 container for QDPX plus native recovery and open artifacts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from io import BytesIO
from pathlib import PurePosixPath
from uuid import UUID
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile, ZipInfo

from qunxue_api.modules.research_exchange.model import (
    ExchangeLoss,
    ExchangeLossSeverity,
    ExchangeReport,
)

_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
_MAX_ARCHIVE_BYTES = 4 * 1024 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class ArchiveArtifact:
    path: str
    media_type: str
    content: bytes

    def __post_init__(self) -> None:
        path = PurePosixPath(self.path)
        if path.is_absolute() or ".." in path.parts or not self.path.strip():
            raise ValueError("archive artifact path is unsafe")
        if self.path.startswith("data/"):
            raise ValueError("archive artifact path is relative to the BagIt payload")
        if not self.media_type.strip():
            raise ValueError("archive artifact media type is required")


@dataclass(frozen=True, slots=True)
class ResearchProjectArchive:
    payload: bytes
    sha256: str


@dataclass(frozen=True, slots=True)
class OpenedResearchProjectArchive:
    valid: bool
    errors: tuple[str, ...]
    qdpx: bytes
    recovery_manifest: dict[str, object]
    exchange_report: ExchangeReport
    audit_events: tuple[dict[str, object], ...]
    artifacts: tuple[ArchiveArtifact, ...]


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _loss_dict(loss: ExchangeLoss) -> dict[str, object]:
    value = asdict(loss)
    value["severity"] = loss.severity.value
    return value


def _report_dict(report: ExchangeReport) -> dict[str, object]:
    return {
        "format": report.format,
        "specification_version": report.specification_version,
        "validation_scope": report.validation_scope,
        "losses": [_loss_dict(loss) for loss in report.losses],
        "identities": [
            {
                "object_type": identity.object_type,
                "native_id": identity.native_id,
                "exchange_guid": str(identity.exchange_guid),
            }
            for identity in report.identities
        ],
    }


def _report_markdown(report: ExchangeReport) -> bytes:
    lines = [
        "# Exchange loss report",
        "",
        f"- Format: {report.format} {report.specification_version}",
        f"- Validation: {report.validation_scope}",
        f"- Loss items: {len(report.losses)}",
        "",
        "| Severity | Object | Field | Disposition | Reason |",
        "| --- | --- | --- | --- | --- |",
    ]
    for loss in report.losses:
        reason = loss.reason.replace("|", "\\|")
        lines.append(
            f"| {loss.severity.value} | {loss.object_type}:{loss.object_id} | "
            f"{loss.field} | {loss.disposition} | {reason} |"
        )
    return ("\n".join(lines) + "\n").encode("utf-8")


def _manifest(files: dict[str, bytes], prefix: str) -> bytes:
    return "".join(
        f"{hashlib.sha256(files[path]).hexdigest()}  {path}\n"
        for path in sorted(files)
        if path.startswith(prefix)
    ).encode("utf-8")


def _zip_info(path: str) -> ZipInfo:
    info = ZipInfo(path, date_time=_ZIP_TIMESTAMP)
    info.compress_type = ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    info.create_system = 3
    return info


def build_research_project_archive(
    *,
    archive_id: UUID,
    task_id: UUID,
    qdpx: bytes,
    recovery_manifest: dict[str, object],
    exchange_report: ExchangeReport,
    audit_events: tuple[dict[str, object], ...],
    artifacts: tuple[ArchiveArtifact, ...] = (),
) -> ResearchProjectArchive:
    payload_files: dict[str, bytes] = {
        "data/exchange/project.qdpx": qdpx,
        "data/project.json": _json_bytes(recovery_manifest),
        "data/reports/exchange-loss.json": _json_bytes(_report_dict(exchange_report)),
        "data/reports/exchange-loss.md": _report_markdown(exchange_report),
        "data/audit/events.ndjson": b"".join(_json_bytes(event) for event in audit_events),
    }
    media_types: dict[str, str] = {
        "data/exchange/project.qdpx": "application/vnd.qdpx",
        "data/project.json": "application/json",
        "data/reports/exchange-loss.json": "application/json",
        "data/reports/exchange-loss.md": "text/markdown",
        "data/audit/events.ndjson": "application/x-ndjson",
    }
    for artifact in artifacts:
        path = f"data/{artifact.path}"
        if path in payload_files:
            raise ValueError(f"duplicate archive artifact: {artifact.path}")
        payload_files[path] = artifact.content
        media_types[path] = artifact.media_type
    payload_files["data/artifacts.json"] = _json_bytes(
        [
            {
                "path": path.removeprefix("data/"),
                "media_type": media_types[path],
                "sha256": hashlib.sha256(content).hexdigest(),
                "size_bytes": len(content),
            }
            for path, content in sorted(payload_files.items())
        ]
    )

    tag_files: dict[str, bytes] = {
        "bagit.txt": b"BagIt-Version: 1.0\nTag-File-Character-Encoding: UTF-8\n",
        "bag-info.txt": (
            f"External-Identifier: {archive_id}\n"
            f"Source-Organization: Qunxue\n"
            f"Bag-Group-Identifier: {task_id}\n"
            "Payload-Oxum: "
            f"{sum(len(value) for value in payload_files.values())}.{len(payload_files)}\n"
        ).encode(),
        "manifest-sha256.txt": _manifest(payload_files, "data/"),
    }
    tag_files["tagmanifest-sha256.txt"] = _manifest(tag_files, "")
    all_files = {**payload_files, **tag_files}
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        for path in sorted(all_files):
            archive.writestr(_zip_info(path), all_files[path])
    payload = output.getvalue()
    return ResearchProjectArchive(payload=payload, sha256=hashlib.sha256(payload).hexdigest())


def _parse_report(value: dict[str, object]) -> ExchangeReport:
    raw_losses = value.get("losses", [])
    assert isinstance(raw_losses, list)
    return ExchangeReport(
        format=str(value.get("format", "REFI-QDA Project")),
        specification_version=str(value.get("specification_version", "1.0")),
        validation_scope=str(value.get("validation_scope", "official-xsd")),
        losses=tuple(
            ExchangeLoss(
                object_type=str(item["object_type"]),
                object_id=str(item["object_id"]),
                field=str(item["field"]),
                reason=str(item["reason"]),
                disposition=str(item["disposition"]),
                severity=ExchangeLossSeverity(str(item.get("severity", "warning"))),
            )
            for item in raw_losses
            if isinstance(item, dict)
        ),
    )


def open_research_project_archive(payload: bytes) -> OpenedResearchProjectArchive:
    errors: list[str] = []
    try:
        with ZipFile(BytesIO(payload)) as archive:
            members = tuple(archive.infolist())
            total = 0
            seen: set[str] = set()
            files: dict[str, bytes] = {}
            for member in members:
                path = PurePosixPath(member.filename)
                if path.is_absolute() or ".." in path.parts or "\\" in member.filename:
                    raise ValueError(f"unsafe archive member: {member.filename}")
                if member.filename in seen:
                    raise ValueError(f"duplicate archive member: {member.filename}")
                seen.add(member.filename)
                total += member.file_size
                if total > _MAX_ARCHIVE_BYTES:
                    raise ValueError("research archive exceeds the size limit")
                files[member.filename] = archive.read(member)
    except (BadZipFile, ValueError) as error:
        return OpenedResearchProjectArchive(
            valid=False,
            errors=(str(error),),
            qdpx=b"",
            recovery_manifest={},
            exchange_report=ExchangeReport(),
            audit_events=(),
            artifacts=(),
        )
    required = {
        "bagit.txt",
        "manifest-sha256.txt",
        "tagmanifest-sha256.txt",
        "data/exchange/project.qdpx",
        "data/project.json",
        "data/reports/exchange-loss.json",
        "data/audit/events.ndjson",
    }
    for path in sorted(required - files.keys()):
        errors.append(f"missing required archive member: {path}")
    for manifest_name in ("manifest-sha256.txt", "tagmanifest-sha256.txt"):
        content = files.get(manifest_name, b"").decode("utf-8", errors="replace")
        for line in content.splitlines():
            try:
                digest, path = line.split("  ", 1)
                actual = hashlib.sha256(files[path]).hexdigest()
            except (ValueError, KeyError):
                errors.append(f"invalid manifest entry in {manifest_name}: {line}")
                continue
            if digest != actual:
                errors.append(f"checksum mismatch: {path}")
    try:
        recovery = json.loads(files.get("data/project.json", b"{}"))
        report = _parse_report(json.loads(files.get("data/reports/exchange-loss.json", b"{}")))
        audit_events = tuple(
            json.loads(line)
            for line in files.get("data/audit/events.ndjson", b"").splitlines()
            if line.strip()
        )
    except (json.JSONDecodeError, AssertionError, KeyError, TypeError) as error:
        errors.append(f"invalid research archive JSON: {error}")
        recovery = {}
        report = ExchangeReport()
        audit_events = ()
    system_paths = {
        "data/exchange/project.qdpx",
        "data/project.json",
        "data/reports/exchange-loss.json",
        "data/reports/exchange-loss.md",
        "data/audit/events.ndjson",
        "data/artifacts.json",
    }
    artifacts = tuple(
        ArchiveArtifact(
            path=path.removeprefix("data/"),
            media_type="application/octet-stream",
            content=content,
        )
        for path, content in sorted(files.items())
        if path.startswith("data/") and path not in system_paths
    )
    return OpenedResearchProjectArchive(
        valid=not errors,
        errors=tuple(errors),
        qdpx=files.get("data/exchange/project.qdpx", b""),
        recovery_manifest=recovery if isinstance(recovery, dict) else {},
        exchange_report=report,
        audit_events=tuple(item for item in audit_events if isinstance(item, dict)),
        artifacts=artifacts,
    )
