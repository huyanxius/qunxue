"""Persistence boundary for professional material archive metadata."""

from typing import Protocol, runtime_checkable
from uuid import UUID

from qunxue_api.modules.research_materials.professional import (
    DoiMetadataCandidate,
    LiteratureEntry,
    MaterialArchiveProfile,
    MaterialBatch,
    MaterialCollection,
    MaterialRelation,
    ProfessionalMaterialArchive,
    ResearchCase,
)


@runtime_checkable
class DoiMetadataResolver(Protocol):
    def resolve(self, doi: str) -> DoiMetadataCandidate: ...


@runtime_checkable
class ProfessionalMaterialRepository(Protocol):
    def save_profile(self, profile: MaterialArchiveProfile) -> MaterialArchiveProfile: ...

    def get_profile(
        self, material_id: UUID, *, user_id: UUID, task_id: UUID
    ) -> MaterialArchiveProfile | None: ...

    def save_batch(self, batch: MaterialBatch) -> MaterialBatch: ...

    def save_collection(self, collection: MaterialCollection) -> MaterialCollection: ...

    def save_literature(self, literature: LiteratureEntry) -> LiteratureEntry: ...

    def save_case(self, case: ResearchCase) -> ResearchCase: ...

    def save_relation(self, relation: MaterialRelation) -> MaterialRelation: ...

    def snapshot(self, *, user_id: UUID, task_id: UUID) -> ProfessionalMaterialArchive: ...
