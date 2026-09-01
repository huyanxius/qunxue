from dataclasses import replace
from uuid import UUID

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from qunxue_api.adapters.sqlite.research_cycle_model import ResearchCycleSnapshotRow
from qunxue_api.adapters.sqlite.research_cycle_repository import SqliteResearchCycleRepository
from qunxue_api.modules.research_cycle import (
    ProjectResearchFacts,
    ResearchCycleSnapshot,
)


def test_cycle_repository_reuses_same_basis_and_versions_changed_basis() -> None:
    engine = create_engine("sqlite:///:memory:")
    ResearchCycleSnapshotRow.__table__.create(engine)
    task_id = UUID(int=188)
    first = _snapshot(task_id=task_id, content_hash="sha256:first")
    second = replace(first, content_hash="sha256:second")

    with Session(engine) as session:
        repository = SqliteResearchCycleRepository(session)
        saved = repository.save(first)
        replayed = repository.save(first)
        changed = repository.save(second)
        session.commit()
        versions = repository.list_versions(task_id)

    assert saved.version == replayed.version == 1
    assert changed.version == 2
    assert [item.content_hash for item in versions] == ["sha256:second", "sha256:first"]
    engine.dispose()


def _snapshot(*, task_id: UUID, content_hash: str) -> ResearchCycleSnapshot:
    return ResearchCycleSnapshot(
        schema_version="research-cycle-v1",
        task_id=task_id,
        version=1,
        content_hash=content_hash,
        analysis_content_hash="sha256:analysis",
        theory_plan_id=None,
        theory_plan_version=None,
        evidence=(),
        gaps=(),
        project_facts=ProjectResearchFacts(
            material_count=0,
            material_kinds=(),
            case_count=0,
            case_material_coverage=(),
            consent_scopes=(),
            sensitivity_levels=(),
            pending_deidentification_count=0,
            sampling_batches=(),
            analysis_counts=(("codes", 0), ("memos", 0), ("comparisons", 0)),
        ),
        reporting_hints=(),
        research_map_patch={"nodes": [], "relations": []},
    )
