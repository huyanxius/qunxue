"""SQLite persistence for the task-owned professional material archive."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from qunxue_api.adapters.sqlite.professional_material_model import (
    LiteratureEntryRow,
    MaterialArchiveProfileRow,
    MaterialBatchRow,
    MaterialCollectionRow,
    MaterialRelationRow,
    ResearchCaseRow,
)
from qunxue_api.modules.research_materials.professional import (
    ConsentScope,
    DeidentificationStatus,
    LiteratureEntry,
    MaterialArchiveProfile,
    MaterialBatch,
    MaterialCollection,
    MaterialRelation,
    MaterialRelationType,
    ModelProcessingScope,
    ProfessionalMaterialArchive,
    ResearchCase,
    ResearchRole,
    ResearchStage,
    SensitivityLevel,
)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class SqliteProfessionalMaterialRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def save_profile(self, profile: MaterialArchiveProfile) -> MaterialArchiveProfile:
        values = {
            "material_id": str(profile.material_id),
            "user_id": str(profile.user_id),
            "task_id": str(profile.task_id),
            "research_role": profile.research_role.value,
            "specific_type": profile.specific_type,
            "stage": profile.stage.value,
            "batch_id": str(profile.batch_id) if profile.batch_id else None,
            "tags": list(profile.tags),
            "collection_ids": [str(value) for value in profile.collection_ids],
            "sensitivity": profile.sensitivity.value,
            "consent_scope": profile.consent_scope.value,
            "deidentification_status": profile.deidentification_status.value,
            "model_processing_scope": profile.model_processing_scope.value,
            "created_at": profile.created_at,
            "updated_at": profile.updated_at,
        }
        self._session.execute(
            insert(MaterialArchiveProfileRow)
            .values(**values)
            .on_conflict_do_update(
                index_elements=["material_id"],
                set_={
                    key: value
                    for key, value in values.items()
                    if key not in {"material_id", "created_at"}
                },
            )
        )
        return profile

    def get_profile(
        self, material_id: UUID, *, user_id: UUID, task_id: UUID
    ) -> MaterialArchiveProfile | None:
        row = self._session.scalar(
            select(MaterialArchiveProfileRow).where(
                MaterialArchiveProfileRow.material_id == str(material_id),
                MaterialArchiveProfileRow.user_id == str(user_id),
                MaterialArchiveProfileRow.task_id == str(task_id),
            )
        )
        return self._profile(row)

    def save_batch(self, batch: MaterialBatch) -> MaterialBatch:
        self._session.add(
            MaterialBatchRow(
                batch_id=str(batch.batch_id),
                user_id=str(batch.user_id),
                task_id=str(batch.task_id),
                name=batch.name,
                created_at=batch.created_at,
            )
        )
        self._session.flush()
        return batch

    def save_collection(self, collection: MaterialCollection) -> MaterialCollection:
        self._session.add(
            MaterialCollectionRow(
                collection_id=str(collection.collection_id),
                user_id=str(collection.user_id),
                task_id=str(collection.task_id),
                name=collection.name,
                description=collection.description,
                parent_collection_id=(
                    str(collection.parent_collection_id)
                    if collection.parent_collection_id
                    else None
                ),
                created_at=collection.created_at,
            )
        )
        self._session.flush()
        return collection

    def save_literature(self, literature: LiteratureEntry) -> LiteratureEntry:
        self._session.add(
            LiteratureEntryRow(
                literature_id=str(literature.literature_id),
                user_id=str(literature.user_id),
                task_id=str(literature.task_id),
                item_type=literature.item_type,
                title=literature.title,
                doi=literature.doi,
                csl_data=literature.csl_data,
                attachment_material_ids=[
                    str(value) for value in literature.attachment_material_ids
                ],
                collection_ids=[str(value) for value in literature.collection_ids],
                created_at=literature.created_at,
                updated_at=literature.updated_at,
            )
        )
        self._session.flush()
        return literature

    def save_case(self, case: ResearchCase) -> ResearchCase:
        self._session.add(
            ResearchCaseRow(
                case_id=str(case.case_id),
                user_id=str(case.user_id),
                task_id=str(case.task_id),
                name=case.name,
                description=case.description,
                attributes=case.attributes,
                material_ids=[str(value) for value in case.material_ids],
                created_at=case.created_at,
                updated_at=case.updated_at,
            )
        )
        self._session.flush()
        return case

    def save_relation(self, relation: MaterialRelation) -> MaterialRelation:
        self._session.add(
            MaterialRelationRow(
                relation_id=str(relation.relation_id),
                user_id=str(relation.user_id),
                task_id=str(relation.task_id),
                source_material_id=str(relation.source_material_id),
                target_material_id=str(relation.target_material_id),
                relation_type=relation.relation_type.value,
                note=relation.note,
                created_at=relation.created_at,
            )
        )
        self._session.flush()
        return relation

    def snapshot(self, *, user_id: UUID, task_id: UUID) -> ProfessionalMaterialArchive:
        owner = (str(user_id), str(task_id))
        profiles = self._owned_rows(MaterialArchiveProfileRow, owner)
        batches = self._owned_rows(MaterialBatchRow, owner)
        collections = self._owned_rows(MaterialCollectionRow, owner)
        literature = self._owned_rows(LiteratureEntryRow, owner)
        cases = self._owned_rows(ResearchCaseRow, owner)
        relations = self._owned_rows(MaterialRelationRow, owner)
        return ProfessionalMaterialArchive(
            profiles=tuple(self._profile(row) for row in profiles),
            batches=tuple(self._batch(row) for row in batches),
            collections=tuple(self._collection(row) for row in collections),
            literature=tuple(self._literature(row) for row in literature),
            cases=tuple(self._case(row) for row in cases),
            relations=tuple(self._relation(row) for row in relations),
        )

    def _owned_rows(self, model, owner: tuple[str, str]):
        return self._session.scalars(
            select(model)
            .where(model.user_id == owner[0], model.task_id == owner[1])
            .order_by(model.created_at, next(iter(model.__table__.primary_key.columns)))
        ).all()

    @staticmethod
    def _profile(row: MaterialArchiveProfileRow | None) -> MaterialArchiveProfile | None:
        if row is None:
            return None
        return MaterialArchiveProfile(
            material_id=UUID(row.material_id),
            user_id=UUID(row.user_id),
            task_id=UUID(row.task_id),
            research_role=ResearchRole(row.research_role),
            specific_type=row.specific_type,
            stage=ResearchStage(row.stage),
            batch_id=UUID(row.batch_id) if row.batch_id else None,
            tags=tuple(row.tags),
            sensitivity=SensitivityLevel(row.sensitivity),
            consent_scope=ConsentScope(row.consent_scope),
            deidentification_status=DeidentificationStatus(row.deidentification_status),
            model_processing_scope=ModelProcessingScope(row.model_processing_scope),
            created_at=_utc(row.created_at),
            updated_at=_utc(row.updated_at),
            collection_ids=tuple(UUID(value) for value in row.collection_ids),
        )

    @staticmethod
    def _batch(row: MaterialBatchRow) -> MaterialBatch:
        return MaterialBatch(
            UUID(row.batch_id), UUID(row.user_id), UUID(row.task_id), row.name, _utc(row.created_at)
        )

    @staticmethod
    def _collection(row: MaterialCollectionRow) -> MaterialCollection:
        return MaterialCollection(
            UUID(row.collection_id),
            UUID(row.user_id),
            UUID(row.task_id),
            row.name,
            row.description,
            UUID(row.parent_collection_id) if row.parent_collection_id else None,
            _utc(row.created_at),
        )

    @staticmethod
    def _literature(row: LiteratureEntryRow) -> LiteratureEntry:
        return LiteratureEntry(
            UUID(row.literature_id),
            UUID(row.user_id),
            UUID(row.task_id),
            row.item_type,
            row.title,
            row.doi,
            dict(row.csl_data),
            tuple(UUID(value) for value in row.attachment_material_ids),
            tuple(UUID(value) for value in row.collection_ids),
            _utc(row.created_at),
            _utc(row.updated_at),
        )

    @staticmethod
    def _case(row: ResearchCaseRow) -> ResearchCase:
        return ResearchCase(
            UUID(row.case_id),
            UUID(row.user_id),
            UUID(row.task_id),
            row.name,
            row.description,
            dict(row.attributes),
            tuple(UUID(value) for value in row.material_ids),
            _utc(row.created_at),
            _utc(row.updated_at),
        )

    @staticmethod
    def _relation(row: MaterialRelationRow) -> MaterialRelation:
        return MaterialRelation(
            UUID(row.relation_id),
            UUID(row.user_id),
            UUID(row.task_id),
            UUID(row.source_material_id),
            UUID(row.target_material_id),
            MaterialRelationType(row.relation_type),
            row.note,
            _utc(row.created_at),
        )
