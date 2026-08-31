from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from qunxue_api.adapters.sqlite.professional_material_model import (
    LiteratureEntryRow,
    MaterialArchiveProfileRow,
    MaterialBatchRow,
    MaterialCollectionRow,
    MaterialRelationRow,
    ResearchCaseRow,
)
from qunxue_api.adapters.sqlite.professional_material_repository import (
    SqliteProfessionalMaterialRepository,
)
from qunxue_api.adapters.sqlite.research_material_model import (
    ResearchMaterialBlobRow,
    ResearchMaterialRow,
)
from qunxue_api.adapters.sqlite.research_material_repository import (
    SqliteResearchMaterialRepository,
)
from qunxue_api.modules.research_materials import (
    ConsentScope,
    DeidentificationStatus,
    LiteratureEntry,
    MaterialArchiveProfile,
    MaterialBatch,
    MaterialCollection,
    MaterialKind,
    MaterialRelation,
    MaterialRelationType,
    ModelProcessingScope,
    ResearchCase,
    ResearchRole,
    ResearchStage,
    SensitivityLevel,
)

NOW = datetime(2026, 8, 31, 12, tzinfo=UTC)
USER_ID = UUID(int=1)
TASK_ID = UUID(int=2)


def _tables(engine) -> None:
    for table in (
        ResearchMaterialRow.__table__,
        ResearchMaterialBlobRow.__table__,
        MaterialBatchRow.__table__,
        MaterialCollectionRow.__table__,
        MaterialArchiveProfileRow.__table__,
        LiteratureEntryRow.__table__,
        ResearchCaseRow.__table__,
        MaterialRelationRow.__table__,
    ):
        table.create(engine, checkfirst=True)


def _material(session: Session, key: str, filename: str):
    return SqliteResearchMaterialRepository(session).create(
        user_id=USER_ID,
        task_id=TASK_ID,
        idempotency_key=key,
        filename=filename,
        media_type="text/plain",
        content=f"{filename} 的原文".encode(),
        material_kind=MaterialKind.INTERVIEW_TRANSCRIPT,
        now=NOW,
    )


def test_repository_round_trips_archive_relations_without_copying_materials() -> None:
    engine = create_engine("sqlite:///:memory:")
    _tables(engine)
    with Session(engine) as session:
        first = _material(session, "one", "访谈一.txt")
        second = _material(session, "two", "访谈二.txt")
        repository = SqliteProfessionalMaterialRepository(session)
        batch = repository.save_batch(
            MaterialBatch.create(user_id=USER_ID, task_id=TASK_ID, name="春季田野", now=NOW)
        )
        collection = repository.save_collection(
            MaterialCollection.create(user_id=USER_ID, task_id=TASK_ID, name="照护", now=NOW)
        )
        profile = repository.save_profile(MaterialArchiveProfile.create(
            material_id=first.material_id,
            user_id=USER_ID,
            task_id=TASK_ID,
            research_role=ResearchRole.EMPIRICAL_MATERIAL,
            specific_type="interview_transcript",
            stage=ResearchStage.COLLECTION,
            batch_id=batch.batch_id,
            tags=("照护",),
            sensitivity=SensitivityLevel.SENSITIVE,
            consent_scope=ConsentScope.PROJECT_ONLY,
            deidentification_status=DeidentificationStatus.COMPLETE,
            model_processing_scope=ModelProcessingScope.EXTERNAL_ALLOWED,
            collection_ids=(collection.collection_id,),
            now=NOW,
        ))
        literature = repository.save_literature(LiteratureEntry.create(
            user_id=USER_ID,
            task_id=TASK_ID,
            item_type="article-journal",
            title="Care after Migration",
            doi="10.1234/abc.1",
            csl_data={"issued": {"date-parts": [[2025]]}},
            attachment_material_ids=(first.material_id, second.material_id),
            collection_ids=(collection.collection_id,),
            now=NOW,
        ))
        case = repository.save_case(ResearchCase.create(
            user_id=USER_ID,
            task_id=TASK_ID,
            name="家庭 A",
            attributes={"迁移阶段": "两年内"},
            material_ids=(first.material_id, second.material_id),
            now=NOW,
        ))
        relation = repository.save_relation(MaterialRelation.create(
            user_id=USER_ID,
            task_id=TASK_ID,
            source_material_id=second.material_id,
            target_material_id=first.material_id,
            relation_type=MaterialRelationType.SUPPLEMENTS,
            note="后续访谈",
            now=NOW,
        ))
        session.commit()

        snapshot = repository.snapshot(user_id=USER_ID, task_id=TASK_ID)

    assert snapshot.profiles == (profile,)
    assert snapshot.batches == (batch,)
    assert snapshot.collections == (collection,)
    assert snapshot.literature == (literature,)
    assert snapshot.cases == (case,)
    assert snapshot.relations == (relation,)
    assert literature.attachment_material_ids == (first.material_id, second.material_id)
    assert case.material_ids == (first.material_id, second.material_id)
    engine.dispose()


def test_material_repository_allows_legacy_rows_but_enforces_explicit_model_scope() -> None:
    engine = create_engine("sqlite:///:memory:")
    _tables(engine)
    with Session(engine) as session:
        legacy = _material(session, "legacy", "历史材料.txt")
        restricted = _material(session, "restricted", "受限材料.txt")
        material_repository = SqliteResearchMaterialRepository(session)
        archive_repository = SqliteProfessionalMaterialRepository(session)
        archive_repository.save_profile(MaterialArchiveProfile.create(
            material_id=restricted.material_id,
            user_id=USER_ID,
            task_id=TASK_ID,
            model_processing_scope=ModelProcessingScope.MANUAL_ONLY,
            now=NOW,
        ))
        session.commit()

        assert material_repository.is_external_model_processable(
            legacy.material_id, user_id=USER_ID, task_id=TASK_ID
        ) is True
        assert material_repository.is_external_model_processable(
            restricted.material_id, user_id=USER_ID, task_id=TASK_ID
        ) is False
    engine.dispose()
