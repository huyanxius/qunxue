"""Owner-scoped orchestration for the material-analysis-theory-method loop."""

from collections.abc import Callable
from uuid import UUID

from qunxue_api.application.professional_materials import ProfessionalMaterialsApplication
from qunxue_api.application.research_analysis import ResearchAnalysisApplication
from qunxue_api.modules.research_cycle import (
    ResearchCycleRepository,
    ResearchCycleService,
    ResearchCycleSnapshot,
)
from qunxue_api.modules.research_materials import ResearchMaterialRepository
from qunxue_api.modules.theory_matching import ConfirmedTheoryPlanSnapshot


class ResearchCycleApplication:
    def __init__(
        self,
        *,
        analysis: ResearchAnalysisApplication,
        materials: ResearchMaterialRepository,
        professional_materials: ProfessionalMaterialsApplication,
        get_theory_plan_for_task: Callable[[UUID], ConfirmedTheoryPlanSnapshot | None],
        snapshots: ResearchCycleRepository,
        commit: Callable[[], None] | None = None,
    ) -> None:
        self._analysis = analysis
        self._materials = materials
        self._professional_materials = professional_materials
        self._get_theory_plan_for_task = get_theory_plan_for_task
        self._snapshots = snapshots
        self._commit = commit or (lambda: None)

    def current(self, *, user_id: UUID, task_id: UUID) -> ResearchCycleSnapshot:
        analysis = self._analysis.formal_handoff(user_id=user_id, task_id=task_id)
        materials = self._materials.list(
            user_id=user_id,
            task_id=task_id,
            include_deleted=False,
            limit=500,
            offset=0,
        )
        archive = self._professional_materials.get_archive(
            user_id=user_id,
            task_id=task_id,
        )
        value = self._snapshots.save(
            ResearchCycleService().project(
                analysis=analysis,
                theory_plan=self._get_theory_plan_for_task(task_id),
                materials=materials,
                archive=archive,
            )
        )
        self._commit()
        return value

    def versions(self, *, user_id: UUID, task_id: UUID) -> tuple[ResearchCycleSnapshot, ...]:
        self._analysis.formal_handoff(user_id=user_id, task_id=task_id)
        return self._snapshots.list_versions(task_id)
