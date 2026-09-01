from dataclasses import asdict, replace
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from qunxue_api.adapters.sqlite.research_cycle_model import ResearchCycleSnapshotRow
from qunxue_api.modules.research_cycle import (
    CycleEvidence,
    CycleEvidenceKind,
    EvidenceGapSuggestion,
    GapDestination,
    ProjectResearchFacts,
    ReportingCoverageHint,
    ReportingCoverageStatus,
    ResearchCycleSnapshot,
)


class SqliteResearchCycleRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, snapshot: ResearchCycleSnapshot) -> ResearchCycleSnapshot:
        existing = self._session.scalar(
            select(ResearchCycleSnapshotRow).where(
                ResearchCycleSnapshotRow.task_id == str(snapshot.task_id),
                ResearchCycleSnapshotRow.content_hash == snapshot.content_hash,
            )
        )
        if existing is not None:
            return _from_row(existing)
        latest_version = self._session.scalar(
            select(func.max(ResearchCycleSnapshotRow.version)).where(
                ResearchCycleSnapshotRow.task_id == str(snapshot.task_id)
            )
        )
        value = replace(snapshot, version=(latest_version or 0) + 1)
        self._session.add(
            ResearchCycleSnapshotRow(
                task_id=str(value.task_id),
                version=value.version,
                content_hash=value.content_hash,
                payload=_payload(value),
                created_at=datetime.now(UTC),
            )
        )
        self._session.flush()
        return value

    def latest(self, task_id: UUID) -> ResearchCycleSnapshot | None:
        row = self._session.scalar(
            select(ResearchCycleSnapshotRow)
            .where(ResearchCycleSnapshotRow.task_id == str(task_id))
            .order_by(ResearchCycleSnapshotRow.version.desc())
            .limit(1)
        )
        return _from_row(row) if row is not None else None

    def list_versions(self, task_id: UUID) -> tuple[ResearchCycleSnapshot, ...]:
        rows = self._session.scalars(
            select(ResearchCycleSnapshotRow)
            .where(ResearchCycleSnapshotRow.task_id == str(task_id))
            .order_by(ResearchCycleSnapshotRow.version.desc())
        )
        return tuple(_from_row(row) for row in rows)


def _payload(value: ResearchCycleSnapshot) -> dict[str, object]:
    return {
        "schema_version": value.schema_version,
        "task_id": str(value.task_id),
        "version": value.version,
        "content_hash": value.content_hash,
        "analysis_content_hash": value.analysis_content_hash,
        "theory_plan_id": str(value.theory_plan_id) if value.theory_plan_id else None,
        "theory_plan_version": value.theory_plan_version,
        "evidence": [_json(asdict(item)) for item in value.evidence],
        "gaps": [_json(asdict(item)) for item in value.gaps],
        "project_facts": _json(asdict(value.project_facts)),
        "reporting_hints": [_json(asdict(item)) for item in value.reporting_hints],
        "research_map_patch": value.research_map_patch,
    }


def _json(value):
    if isinstance(value, dict):
        return {key: _json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json(item) for item in value]
    if isinstance(value, UUID):
        return str(value)
    enum_value = getattr(value, "value", None)
    return enum_value if enum_value is not None else value


def _from_row(row: ResearchCycleSnapshotRow) -> ResearchCycleSnapshot:
    value = row.payload
    facts = value["project_facts"]
    return ResearchCycleSnapshot(
        schema_version=str(value["schema_version"]),
        task_id=UUID(str(value["task_id"])),
        version=row.version,
        content_hash=row.content_hash,
        analysis_content_hash=str(value["analysis_content_hash"]),
        theory_plan_id=(
            UUID(str(value["theory_plan_id"])) if value.get("theory_plan_id") else None
        ),
        theory_plan_version=(
            int(value["theory_plan_version"])
            if value.get("theory_plan_version") is not None
            else None
        ),
        evidence=tuple(
            CycleEvidence(
                evidence_ref_id=str(item["evidence_ref_id"]),
                kind=CycleEvidenceKind(str(item["kind"])),
                statement=str(item["statement"]),
                source_kind=str(item["source_kind"]),
                source_id=str(item["source_id"]),
                annotation_id=UUID(str(item["annotation_id"])),
                material_id=UUID(str(item["material_id"])),
                parse_id=UUID(str(item["parse_id"])),
                segment_id=str(item["segment_id"]),
                quote=str(item["quote"]),
                locator=str(item["locator"]),
                case_label=str(item["case_label"]) if item.get("case_label") else None,
                observed_at=str(item["observed_at"]) if item.get("observed_at") else None,
                confirmed=bool(item["confirmed"]),
            )
            for item in value["evidence"]
        ),
        gaps=tuple(
            EvidenceGapSuggestion(
                gap_id=str(item["gap_id"]),
                source_kind=str(item["source_kind"]),
                source_id=str(item["source_id"]),
                description=str(item["description"]),
                suggested_action=str(item["suggested_action"]),
                destination=GapDestination(str(item["destination"])),
                priority=str(item["priority"]),
                analysis_content_hash=str(item["analysis_content_hash"]),
                theory_plan_id=(
                    UUID(str(item["theory_plan_id"])) if item.get("theory_plan_id") else None
                ),
                theory_plan_version=(
                    int(item["theory_plan_version"])
                    if item.get("theory_plan_version") is not None
                    else None
                ),
                status=str(item["status"]),
            )
            for item in value["gaps"]
        ),
        project_facts=ProjectResearchFacts(
            material_count=int(facts["material_count"]),
            material_kinds=_pairs(facts["material_kinds"]),
            case_count=int(facts["case_count"]),
            case_material_coverage=_pairs(facts["case_material_coverage"]),
            consent_scopes=_pairs(facts["consent_scopes"]),
            sensitivity_levels=_pairs(facts["sensitivity_levels"]),
            pending_deidentification_count=int(facts["pending_deidentification_count"]),
            sampling_batches=tuple(str(item) for item in facts["sampling_batches"]),
            analysis_counts=_pairs(facts["analysis_counts"]),
        ),
        reporting_hints=tuple(
            ReportingCoverageHint(
                guideline=str(item["guideline"]),
                item_key=str(item["item_key"]),
                label=str(item["label"]),
                status=ReportingCoverageStatus(str(item["status"])),
                message=str(item["message"]),
                blocking=bool(item["blocking"]),
            )
            for item in value["reporting_hints"]
        ),
        research_map_patch=value["research_map_patch"],
    )


def _pairs(value) -> tuple[tuple[str, int], ...]:
    return tuple((str(item[0]), int(item[1])) for item in value)
