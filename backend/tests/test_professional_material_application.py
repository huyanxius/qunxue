from datetime import UTC, datetime
from uuid import UUID

import pytest
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
from qunxue_api.adapters.sqlite.research_material_repository import SqliteResearchMaterialRepository
from qunxue_api.application.professional_materials import ProfessionalMaterialsApplication
from qunxue_api.modules.research_materials import (
    DeidentificationStatus,
    DoiMetadataCandidate,
    LiteratureExchangeFormat,
    MaterialKind,
    ModelProcessingScope,
)

NOW = datetime(2026, 8, 31, 12, tzinfo=UTC)
USER_ID = UUID(int=1)
TASK_ID = UUID(int=2)


class _Tasks:
    def get(self, task_id: UUID, user_id: UUID):
        return object() if (task_id, user_id) == (TASK_ID, USER_ID) else None


def _tables(engine) -> None:
    for table in (
        ResearchMaterialRow.__table__, ResearchMaterialBlobRow.__table__,
        MaterialBatchRow.__table__, MaterialCollectionRow.__table__,
        MaterialArchiveProfileRow.__table__, LiteratureEntryRow.__table__,
        ResearchCaseRow.__table__, MaterialRelationRow.__table__,
    ):
        table.create(engine, checkfirst=True)


def _upload(repository: SqliteResearchMaterialRepository, key: str, filename: str):
    return repository.create(
        user_id=USER_ID, task_id=TASK_ID, idempotency_key=key,
        filename=filename, media_type="text/plain", content=f"{filename}原文".encode(),
        material_kind=MaterialKind.INTERVIEW_TRANSCRIPT, now=NOW,
    )


def test_newly_cataloged_material_is_manual_readable_but_inventory_flags_ethics_work() -> None:
    engine = create_engine("sqlite:///:memory:")
    _tables(engine)
    with Session(engine) as session:
        materials = SqliteResearchMaterialRepository(session)
        material = _upload(materials, "one", "访谈.txt")
        application = ProfessionalMaterialsApplication(
            archive=SqliteProfessionalMaterialRepository(session),
            materials=materials,
            research_tasks=_Tasks(),
            clock=lambda: NOW,
            commit=session.commit,
        )

        profile = application.ensure_profile(
            user_id=USER_ID,
            task_id=TASK_ID,
            material_id=material.material_id,
        )
        view = application.get_archive(user_id=USER_ID, task_id=TASK_ID)

    assert profile.model_processing_scope is ModelProcessingScope.NOT_ASSESSED
    assert profile.deidentification_status is DeidentificationStatus.PENDING
    assert profile.allows_manual_reading is True
    assert view.inventory.pending_deidentification_material_ids == (material.material_id,)
    assert view.inventory.restricted_material_ids == (material.material_id,)
    engine.dispose()


def test_import_keeps_duplicate_literature_entries_separate_and_reports_reasons() -> None:
    engine = create_engine("sqlite:///:memory:")
    _tables(engine)
    with Session(engine) as session:
        application = ProfessionalMaterialsApplication(
            archive=SqliteProfessionalMaterialRepository(session),
            materials=SqliteResearchMaterialRepository(session),
            research_tasks=_Tasks(),
            clock=lambda: NOW,
            commit=session.commit,
        )
        payload = b"""[
          {"id":"one","type":"article-journal","title":"Care after Migration",
           "DOI":"10.1234/ABC.1"},
          {"id":"two","type":"article-journal","title":"Imported title differs",
           "DOI":"https://doi.org/10.1234/abc.1"}
        ]"""

        created = application.import_literature(
            user_id=USER_ID, task_id=TASK_ID,
            exchange_format=LiteratureExchangeFormat.CSL_JSON, payload=payload,
        )
        view = application.get_archive(user_id=USER_ID, task_id=TASK_ID)

    assert len(created) == 2
    assert created[0].literature_id != created[1].literature_id
    assert view.duplicate_hints[0].reasons == ("same_doi",)
    assert set(view.inventory.suspected_duplicate_literature_ids) == {
        created[0].literature_id, created[1].literature_id,
    }
    engine.dispose()


def test_case_cannot_link_material_from_another_task() -> None:
    engine = create_engine("sqlite:///:memory:")
    _tables(engine)
    with Session(engine) as session:
        application = ProfessionalMaterialsApplication(
            archive=SqliteProfessionalMaterialRepository(session),
            materials=SqliteResearchMaterialRepository(session),
            research_tasks=_Tasks(), clock=lambda: NOW, commit=session.commit,
        )

        with pytest.raises(ValueError, match="material does not belong"):
            application.create_case(
                user_id=USER_ID, task_id=TASK_ID, name="家庭 A", attributes={},
                material_ids=(UUID(int=999),),
            )
    engine.dispose()


def test_doi_metadata_check_stays_behind_the_application_adapter_boundary() -> None:
    class _Resolver:
        def resolve(self, doi: str) -> DoiMetadataCandidate:
            assert doi == "10.1234/abc.1"
            return DoiMetadataCandidate(
                doi=doi,
                item_type="article-journal",
                title="Care after Migration",
                csl_data={"DOI": doi},
                source="test",
                verified_at=NOW,
            )

    engine = create_engine("sqlite:///:memory:")
    _tables(engine)
    with Session(engine) as session:
        application = ProfessionalMaterialsApplication(
            archive=SqliteProfessionalMaterialRepository(session),
            materials=SqliteResearchMaterialRepository(session),
            research_tasks=_Tasks(), clock=lambda: NOW, commit=session.commit,
            doi_resolver=_Resolver(),
        )

        candidate = application.resolve_doi(
            user_id=USER_ID, task_id=TASK_ID, doi="10.1234/abc.1"
        )

    assert candidate.title == "Care after Migration"
    engine.dispose()
