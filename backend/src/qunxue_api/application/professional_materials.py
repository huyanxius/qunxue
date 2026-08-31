"""Task-owned use cases for cataloging professional research materials."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

from qunxue_api.modules.research_intake import ResearchTaskRepository
from qunxue_api.modules.research_materials import (
    ConsentScope,
    DeidentificationStatus,
    DoiMetadataCandidate,
    DoiMetadataResolver,
    LiteratureDuplicateHint,
    LiteratureEntry,
    LiteratureExchangeFormat,
    MaterialArchiveInventory,
    MaterialArchiveProfile,
    MaterialBatch,
    MaterialCollection,
    MaterialKind,
    MaterialRelation,
    MaterialRelationType,
    MaterialStatus,
    ModelProcessingScope,
    ProfessionalMaterialArchiveView,
    ProfessionalMaterialRepository,
    ResearchCase,
    ResearchMaterial,
    ResearchMaterialRepository,
    ResearchRole,
    ResearchStage,
    SensitivityLevel,
    export_literature_entries,
    import_literature_entries,
)


class ProfessionalMaterialsApplication:
    def __init__(
        self,
        *,
        archive: ProfessionalMaterialRepository,
        materials: ResearchMaterialRepository,
        research_tasks: ResearchTaskRepository,
        clock=None,
        commit=None,
        doi_resolver: DoiMetadataResolver | None = None,
    ) -> None:
        self._archive = archive
        self._materials = materials
        self._research_tasks = research_tasks
        self._clock = clock or (lambda: datetime.now(UTC))
        self._commit = commit or (lambda: None)
        self._doi_resolver = doi_resolver

    def resolve_doi(
        self, *, user_id: UUID, task_id: UUID, doi: str
    ) -> DoiMetadataCandidate:
        self._require_task(user_id=user_id, task_id=task_id)
        if self._doi_resolver is None:
            raise RuntimeError("DOI metadata resolver is unavailable")
        return self._doi_resolver.resolve(doi)

    def ensure_profile(
        self, *, user_id: UUID, task_id: UUID, material_id: UUID
    ) -> MaterialArchiveProfile:
        material = self._material(user_id=user_id, task_id=task_id, material_id=material_id)
        current = self._archive.get_profile(material_id, user_id=user_id, task_id=task_id)
        if current is not None:
            return current
        profile = MaterialArchiveProfile.create(
            material_id=material.material_id,
            user_id=user_id,
            task_id=task_id,
            research_role=(
                ResearchRole.LITERATURE
                if material.material_kind is MaterialKind.PAPER
                else ResearchRole.EMPIRICAL_MATERIAL
            ),
            specific_type=material.material_kind.value,
            now=self._clock(),
        )
        self._archive.save_profile(profile)
        self._commit()
        return profile

    def update_profile(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        material_id: UUID,
        research_role: ResearchRole,
        specific_type: str,
        stage: ResearchStage,
        batch_id: UUID | None,
        tags: tuple[str, ...],
        collection_ids: tuple[UUID, ...],
        sensitivity: SensitivityLevel,
        consent_scope: ConsentScope,
        deidentification_status: DeidentificationStatus,
        model_processing_scope: ModelProcessingScope,
    ) -> MaterialArchiveProfile:
        current = self.ensure_profile(user_id=user_id, task_id=task_id, material_id=material_id)
        self._assert_collection_ids(user_id=user_id, task_id=task_id, values=collection_ids)
        if batch_id is not None:
            snapshot = self._archive.snapshot(user_id=user_id, task_id=task_id)
            batch_ids = {item.batch_id for item in snapshot.batches}
            if batch_id not in batch_ids:
                raise ValueError("batch does not belong to the research task")
        updated = replace(
            current,
            research_role=ResearchRole(research_role),
            specific_type=specific_type.strip(),
            stage=ResearchStage(stage),
            batch_id=batch_id,
            tags=tuple(dict.fromkeys(value.strip() for value in tags if value.strip())),
            collection_ids=tuple(dict.fromkeys(collection_ids)),
            sensitivity=SensitivityLevel(sensitivity),
            consent_scope=ConsentScope(consent_scope),
            deidentification_status=DeidentificationStatus(deidentification_status),
            model_processing_scope=ModelProcessingScope(model_processing_scope),
            updated_at=self._clock(),
        )
        if not updated.specific_type:
            raise ValueError("specific_type is required")
        self._archive.save_profile(updated)
        self._commit()
        return updated

    def create_batch(self, *, user_id: UUID, task_id: UUID, name: str) -> MaterialBatch:
        self._require_task(user_id=user_id, task_id=task_id)
        value = self._archive.save_batch(
            MaterialBatch.create(user_id=user_id, task_id=task_id, name=name, now=self._clock())
        )
        self._commit()
        return value

    def create_collection(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        name: str,
        description: str | None = None,
        parent_collection_id: UUID | None = None,
    ) -> MaterialCollection:
        self._require_task(user_id=user_id, task_id=task_id)
        if parent_collection_id is not None:
            self._assert_collection_ids(
                user_id=user_id, task_id=task_id, values=(parent_collection_id,)
            )
        value = self._archive.save_collection(
            MaterialCollection.create(
                user_id=user_id,
                task_id=task_id,
                name=name,
                description=description,
                parent_collection_id=parent_collection_id,
                now=self._clock(),
            )
        )
        self._commit()
        return value

    def create_literature(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        item_type: str,
        title: str,
        doi: str | None,
        csl_data: dict[str, object],
        attachment_material_ids: tuple[UUID, ...] = (),
        collection_ids: tuple[UUID, ...] = (),
    ) -> LiteratureEntry:
        self._require_task(user_id=user_id, task_id=task_id)
        self._assert_material_ids(
            user_id=user_id, task_id=task_id, values=attachment_material_ids
        )
        self._assert_collection_ids(user_id=user_id, task_id=task_id, values=collection_ids)
        value = self._archive.save_literature(
            LiteratureEntry.create(
                user_id=user_id,
                task_id=task_id,
                item_type=item_type,
                title=title,
                doi=doi,
                csl_data=csl_data,
                attachment_material_ids=attachment_material_ids,
                collection_ids=collection_ids,
                now=self._clock(),
            )
        )
        self._commit()
        return value

    def import_literature(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        exchange_format: LiteratureExchangeFormat,
        payload: bytes,
        collection_ids: tuple[UUID, ...] = (),
    ) -> tuple[LiteratureEntry, ...]:
        self._require_task(user_id=user_id, task_id=task_id)
        self._assert_collection_ids(user_id=user_id, task_id=task_id, values=collection_ids)
        values = tuple(
            self._archive.save_literature(
                LiteratureEntry.create(
                    user_id=user_id,
                    task_id=task_id,
                    item_type=record.item_type,
                    title=record.title,
                    doi=record.doi,
                    csl_data=record.csl_data,
                    collection_ids=collection_ids,
                    now=self._clock(),
                )
            )
            for record in import_literature_entries(exchange_format, payload)
        )
        self._commit()
        return values

    def export_literature(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        exchange_format: LiteratureExchangeFormat,
    ) -> bytes:
        self._require_task(user_id=user_id, task_id=task_id)
        entries = self._archive.snapshot(user_id=user_id, task_id=task_id).literature
        return export_literature_entries(exchange_format, entries)

    def create_case(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        name: str,
        attributes: dict[str, str | int | float | bool | None],
        material_ids: tuple[UUID, ...] = (),
        description: str | None = None,
    ) -> ResearchCase:
        self._require_task(user_id=user_id, task_id=task_id)
        self._assert_material_ids(user_id=user_id, task_id=task_id, values=material_ids)
        value = self._archive.save_case(
            ResearchCase.create(
                user_id=user_id,
                task_id=task_id,
                name=name,
                description=description,
                attributes=attributes,
                material_ids=material_ids,
                now=self._clock(),
            )
        )
        self._commit()
        return value

    def create_relation(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        source_material_id: UUID,
        target_material_id: UUID,
        relation_type: MaterialRelationType,
        note: str | None = None,
    ) -> MaterialRelation:
        self._require_task(user_id=user_id, task_id=task_id)
        self._assert_material_ids(
            user_id=user_id,
            task_id=task_id,
            values=(source_material_id, target_material_id),
        )
        value = self._archive.save_relation(
            MaterialRelation.create(
                user_id=user_id,
                task_id=task_id,
                source_material_id=source_material_id,
                target_material_id=target_material_id,
                relation_type=relation_type,
                note=note,
                now=self._clock(),
            )
        )
        self._commit()
        return value

    def get_archive(
        self, *, user_id: UUID, task_id: UUID
    ) -> ProfessionalMaterialArchiveView:
        self._require_task(user_id=user_id, task_id=task_id)
        archive = self._archive.snapshot(user_id=user_id, task_id=task_id)
        materials = self._materials.list(
            user_id=user_id, task_id=task_id, include_deleted=False, limit=500, offset=0
        )
        profiles = {profile.material_id: profile for profile in archive.profiles}
        duplicate_hints: list[LiteratureDuplicateHint] = []
        duplicate_ids: set[UUID] = set()
        for index, entry in enumerate(archive.literature):
            for candidate in archive.literature[index + 1 :]:
                reasons = entry.duplicate_reasons(candidate)
                if not reasons:
                    continue
                duplicate_hints.append(
                    LiteratureDuplicateHint(entry.literature_id, candidate.literature_id, reasons)
                )
                duplicate_ids.update((entry.literature_id, candidate.literature_id))
        inventory = MaterialArchiveInventory(
            catalog_pending_material_ids=tuple(
                material.material_id
                for material in materials
                if material.material_id not in profiles
            ),
            parse_failed_material_ids=tuple(
                material.material_id
                for material in materials
                if material.status is MaterialStatus.FAILED
            ),
            suspected_duplicate_literature_ids=tuple(sorted(duplicate_ids, key=str)),
            pending_deidentification_material_ids=tuple(
                profile.material_id
                for profile in archive.profiles
                if profile.deidentification_status is DeidentificationStatus.PENDING
            ),
            restricted_material_ids=tuple(
                profile.material_id
                for profile in archive.profiles
                if not profile.allows_external_model_processing
            ),
        )
        return ProfessionalMaterialArchiveView(archive, inventory, tuple(duplicate_hints))

    def _assert_material_ids(
        self, *, user_id: UUID, task_id: UUID, values: tuple[UUID, ...]
    ) -> None:
        for material_id in values:
            if self._materials.get(material_id, user_id=user_id, task_id=task_id) is None:
                raise ValueError("material does not belong to the research task")

    def _assert_collection_ids(
        self, *, user_id: UUID, task_id: UUID, values: tuple[UUID, ...]
    ) -> None:
        if not values:
            return
        available = {
            item.collection_id
            for item in self._archive.snapshot(user_id=user_id, task_id=task_id).collections
        }
        if any(value not in available for value in values):
            raise ValueError("collection does not belong to the research task")

    def _material(self, *, user_id: UUID, task_id: UUID, material_id: UUID) -> ResearchMaterial:
        self._require_task(user_id=user_id, task_id=task_id)
        material = self._materials.get(material_id, user_id=user_id, task_id=task_id)
        if material is None:
            raise ValueError("material does not belong to the research task")
        return material

    def _require_task(self, *, user_id: UUID, task_id: UUID) -> None:
        if self._research_tasks.get(task_id, user_id) is None:
            from qunxue_api.modules.research_intake import ResearchTaskNotFound

            raise ResearchTaskNotFound(str(task_id))
