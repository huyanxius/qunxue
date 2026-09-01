from dataclasses import asdict
from uuid import UUID

from pydantic import BaseModel

from qunxue_api.modules.research_cycle import ResearchCycleSnapshot


class CycleEvidenceResponse(BaseModel):
    evidence_ref_id: str
    kind: str
    statement: str
    source_kind: str
    source_id: str
    annotation_id: UUID
    material_id: UUID
    parse_id: UUID
    segment_id: str
    quote: str
    locator: str
    case_label: str | None
    observed_at: str | None
    confirmed: bool


class EvidenceGapResponse(BaseModel):
    gap_id: str
    source_kind: str
    source_id: str
    description: str
    suggested_action: str
    destination: str
    priority: str
    analysis_content_hash: str
    theory_plan_id: UUID | None
    theory_plan_version: int | None
    status: str


class ReportingCoverageResponse(BaseModel):
    guideline: str
    item_key: str
    label: str
    status: str
    message: str
    blocking: bool


class ProjectResearchFactsResponse(BaseModel):
    material_count: int
    material_kinds: list[list[str | int]]
    case_count: int
    case_material_coverage: list[list[str | int]]
    consent_scopes: list[list[str | int]]
    sensitivity_levels: list[list[str | int]]
    pending_deidentification_count: int
    sampling_batches: list[str]
    analysis_counts: list[list[str | int]]


class ResearchCycleResponse(BaseModel):
    schema_version: str
    task_id: UUID
    version: int
    content_hash: str
    analysis_content_hash: str
    theory_plan_id: UUID | None
    theory_plan_version: int | None
    evidence: list[CycleEvidenceResponse]
    gaps: list[EvidenceGapResponse]
    project_facts: ProjectResearchFactsResponse
    reporting_hints: list[ReportingCoverageResponse]
    research_map_patch: dict[str, list[dict[str, object]]]

    @classmethod
    def from_domain(cls, value: ResearchCycleSnapshot) -> "ResearchCycleResponse":
        facts = value.project_facts
        return cls(
            schema_version=value.schema_version,
            task_id=value.task_id,
            version=value.version,
            content_hash=value.content_hash,
            analysis_content_hash=value.analysis_content_hash,
            theory_plan_id=value.theory_plan_id,
            theory_plan_version=value.theory_plan_version,
            evidence=[
                CycleEvidenceResponse(
                    **{
                        **asdict(item),
                        "kind": item.kind.value,
                    }
                )
                for item in value.evidence
            ],
            gaps=[
                EvidenceGapResponse(
                    **{
                        **asdict(item),
                        "destination": item.destination.value,
                    }
                )
                for item in value.gaps
            ],
            project_facts=ProjectResearchFactsResponse(
                material_count=facts.material_count,
                material_kinds=[list(item) for item in facts.material_kinds],
                case_count=facts.case_count,
                case_material_coverage=[list(item) for item in facts.case_material_coverage],
                consent_scopes=[list(item) for item in facts.consent_scopes],
                sensitivity_levels=[list(item) for item in facts.sensitivity_levels],
                pending_deidentification_count=facts.pending_deidentification_count,
                sampling_batches=list(facts.sampling_batches),
                analysis_counts=[list(item) for item in facts.analysis_counts],
            ),
            reporting_hints=[
                ReportingCoverageResponse(
                    guideline=item.guideline,
                    item_key=item.item_key,
                    label=item.label,
                    status=item.status.value,
                    message=item.message,
                    blocking=item.blocking,
                )
                for item in value.reporting_hints
            ],
            research_map_patch=value.research_map_patch,
        )


class ResearchCycleVersionListResponse(BaseModel):
    task_id: UUID
    items: list[ResearchCycleResponse]
