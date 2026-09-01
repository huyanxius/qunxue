from typing import Protocol
from uuid import UUID

from qunxue_api.modules.research_cycle.domain import ResearchCycleSnapshot


class ResearchCycleRepository(Protocol):
    def save(self, snapshot: ResearchCycleSnapshot) -> ResearchCycleSnapshot: ...
    def latest(self, task_id: UUID) -> ResearchCycleSnapshot | None: ...
    def list_versions(self, task_id: UUID) -> tuple[ResearchCycleSnapshot, ...]: ...
