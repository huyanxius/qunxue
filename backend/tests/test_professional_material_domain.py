from datetime import UTC, datetime
from uuid import UUID

import pytest

from qunxue_api.modules.research_materials import (
    ConsentScope,
    DeidentificationStatus,
    LiteratureEntry,
    MaterialArchiveProfile,
    MaterialRelation,
    MaterialRelationType,
    ModelProcessingScope,
    ResearchCase,
    ResearchRole,
    ResearchStage,
    SensitivityLevel,
)

NOW = datetime(2026, 8, 31, 12, tzinfo=UTC)


def test_profile_normalizes_tags_and_blocks_unapproved_model_processing() -> None:
    profile = MaterialArchiveProfile.create(
        material_id=UUID(int=1),
        user_id=UUID(int=2),
        task_id=UUID(int=3),
        research_role=ResearchRole.EMPIRICAL_MATERIAL,
        specific_type="interview_transcript",
        stage=ResearchStage.COLLECTION,
        tags=(" 迁移 ", "照护", "迁移"),
        sensitivity=SensitivityLevel.SENSITIVE,
        consent_scope=ConsentScope.PROJECT_ONLY,
        deidentification_status=DeidentificationStatus.PENDING,
        model_processing_scope=ModelProcessingScope.MANUAL_ONLY,
        now=NOW,
    )

    assert profile.tags == ("迁移", "照护")
    assert profile.allows_manual_reading is True
    assert profile.allows_external_model_processing is False


def test_literature_entry_normalizes_doi_without_silently_merging_duplicates() -> None:
    first = LiteratureEntry.create(
        literature_id=UUID(int=10),
        user_id=UUID(int=2),
        task_id=UUID(int=3),
        item_type="article-journal",
        title="Care after Migration",
        doi="https://doi.org/10.1234/ABC.1",
        csl_data={
            "author": [{"family": "Li", "given": "Ming"}],
            "issued": {"date-parts": [[2025]]},
        },
        attachment_material_ids=(UUID(int=20),),
        collection_ids=(UUID(int=30),),
        now=NOW,
    )
    duplicate = LiteratureEntry.create(
        literature_id=UUID(int=11),
        user_id=UUID(int=2),
        task_id=UUID(int=3),
        item_type="article-journal",
        title="A different imported title",
        doi="doi:10.1234/abc.1",
        csl_data={},
        now=NOW,
    )

    assert first.doi == duplicate.doi == "10.1234/abc.1"
    assert first.literature_id != duplicate.literature_id
    assert first.duplicate_reasons(duplicate) == ("same_doi",)


def test_case_attributes_are_filterable_scalars_not_replacement_source_text() -> None:
    case = ResearchCase.create(
        case_id=UUID(int=40),
        user_id=UUID(int=2),
        task_id=UUID(int=3),
        name="家庭 A",
        attributes={"迁移阶段": "两年内", "儿童数": 2, "单亲": False},
        material_ids=(UUID(int=20), UUID(int=21)),
        now=NOW,
    )

    assert case.attributes["儿童数"] == 2
    assert case.material_ids == (UUID(int=20), UUID(int=21))

    with pytest.raises(ValueError, match="scalar"):
        ResearchCase.create(
            case_id=UUID(int=41),
            user_id=UUID(int=2),
            task_id=UUID(int=3),
            name="家庭 B",
            attributes={"不合法": {"嵌套": "原文"}},
            now=NOW,
        )


def test_material_relation_rejects_self_links() -> None:
    with pytest.raises(ValueError, match="different materials"):
        MaterialRelation.create(
            relation_id=UUID(int=50),
            user_id=UUID(int=2),
            task_id=UUID(int=3),
            source_material_id=UUID(int=20),
            target_material_id=UUID(int=20),
            relation_type=MaterialRelationType.DERIVED_FROM,
            note=None,
            now=NOW,
        )
