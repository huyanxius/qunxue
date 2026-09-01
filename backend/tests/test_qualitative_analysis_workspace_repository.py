from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from qunxue_api.adapters.sqlite.base import Base
from qunxue_api.adapters.sqlite.research_analysis_repository import (
    SqliteResearchAnalysisRepository,
)
from qunxue_api.modules.research_analysis import (
    AnalysisCaseProfile,
    AnalysisMemoLink,
    AnalysisTheme,
    CaseThemeMatrixCell,
    CodebookEntry,
    CodebookLifecycle,
    ComparisonFindingKind,
    MatrixSubjectKind,
    MemoTargetKind,
    MethodPresetSelection,
    QualitativeMethod,
)

_USER = UUID("10000000-0000-0000-0000-000000000186")
_TASK = UUID("20000000-0000-0000-0000-000000000186")
_NOW = datetime(2026, 8, 31, 8, 0, tzinfo=UTC)


def _records():
    code_id = uuid4()
    annotation_id = uuid4()
    memo_id = uuid4()
    profile = AnalysisCaseProfile.create(
        user_id=_USER,
        task_id=_TASK,
        case_ref="opaque-case-1",
        display_label="访谈个案 1",
        attributes=(("地区", "县城"),),
        summary="主要依靠邻里网络取得服务。",
        annotation_ids=(annotation_id,),
        memo_ids=(memo_id,),
        now=_NOW,
    )
    theme = AnalysisTheme.create(
        user_id=_USER,
        task_id=_TASK,
        label="制度资源的多重入口",
        central_concept="正式组织与非正式网络都可能成为资源入口。",
        code_ids=(code_id,),
        annotation_ids=(annotation_id,),
        source="agent",
        now=_NOW,
    )
    return (
        CodebookEntry.create(
            user_id=_USER,
            task_id=_TASK,
            code_id=code_id,
            inclusion_rules=("明确描述资源进入渠道",),
            exclusion_rules=("只描述一般信息获取",),
            parent_code_id=None,
            positive_example_annotation_ids=(annotation_id,),
            negative_example_annotation_ids=(uuid4(),),
            now=_NOW,
        ),
        theme,
        AnalysisMemoLink.create(
            user_id=_USER,
            task_id=_TASK,
            memo_id=memo_id,
            target_kind=MemoTargetKind.CODE,
            target_ref=str(code_id),
            annotation_ids=(annotation_id,),
            now=_NOW,
        ),
        profile,
        CaseThemeMatrixCell.create(
            user_id=_USER,
            task_id=_TASK,
            case_profile_id=profile.profile_id,
            subject_kind=MatrixSubjectKind.THEME,
            subject_id=theme.theme_id,
            summary="非正式网络构成对组织渠道必要性的反例。",
            annotation_ids=(annotation_id,),
            memo_ids=(memo_id,),
            finding_kinds=(ComparisonFindingKind.COUNTEREXAMPLE,),
            now=_NOW,
        ),
        MethodPresetSelection(
            user_id=_USER,
            task_id=_TASK,
            method=QualitativeMethod.CASE_STUDY,
            version=1,
            updated_at=_NOW,
        ),
    )


def test_repository_round_trips_qualitative_workspace_records() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    entry, theme, link, profile, cell, method = _records()

    with Session(engine) as session:
        repository = SqliteResearchAnalysisRepository(session)
        repository.add_codebook_entry(entry)
        repository.add_theme(theme)
        repository.add_memo_link(link)
        repository.add_case_profile(profile)
        repository.add_matrix_cell(cell)
        repository.add_method_selection(method)
        session.commit()

    with Session(engine) as session:
        repository = SqliteResearchAnalysisRepository(session)
        assert (
            repository.get_codebook_entry(
                entry.code_id,
                user_id=_USER,
                task_id=_TASK,
            )
            == entry
        )
        assert repository.list_codebook_entries(user_id=_USER, task_id=_TASK) == (entry,)
        assert repository.get_theme(theme.theme_id, user_id=_USER, task_id=_TASK) == theme
        assert repository.list_themes(user_id=_USER, task_id=_TASK) == (theme,)
        assert repository.list_memo_links(user_id=_USER, task_id=_TASK) == (link,)
        assert (
            repository.get_case_profile(
                profile.profile_id,
                user_id=_USER,
                task_id=_TASK,
            )
            == profile
        )
        assert repository.list_case_profiles(user_id=_USER, task_id=_TASK) == (profile,)
        assert repository.list_matrix_cells(user_id=_USER, task_id=_TASK) == (cell,)
        assert repository.get_method_selection(user_id=_USER, task_id=_TASK) == method


def test_repository_never_overwrites_newer_workspace_versions_with_stale_records() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    entry, theme, _link, profile, cell, method = _records()
    revised_entry = entry.transition(
        lifecycle=CodebookLifecycle.RETIRED,
        related_code_ids=(),
        expected_version=1,
        reason="不再使用",
        now=_NOW + timedelta(minutes=1),
    )
    confirmed_theme = theme.confirm(
        user_confirmed=True,
        expected_version=1,
        reason="研究者确认",
        now=_NOW + timedelta(minutes=1),
    )
    revised_profile = AnalysisCaseProfile.create(
        user_id=_USER,
        task_id=_TASK,
        case_ref=profile.case_ref,
        display_label=profile.display_label,
        attributes=profile.attributes,
        summary="加入了反例后的个案摘要。",
        annotation_ids=profile.annotation_ids,
        memo_ids=profile.memo_ids,
        now=_NOW + timedelta(minutes=1),
        profile_id=profile.profile_id,
        version=2,
    )
    revised_cell = CaseThemeMatrixCell.create(
        user_id=_USER,
        task_id=_TASK,
        case_profile_id=cell.case_profile_id,
        subject_kind=cell.subject_kind,
        subject_id=cell.subject_id,
        summary="补充了证据缺口。",
        annotation_ids=cell.annotation_ids,
        memo_ids=cell.memo_ids,
        finding_kinds=(
            ComparisonFindingKind.COUNTEREXAMPLE,
            ComparisonFindingKind.EVIDENCE_GAP,
        ),
        now=_NOW + timedelta(minutes=1),
        cell_id=cell.cell_id,
        version=2,
    )
    revised_method = MethodPresetSelection(
        user_id=_USER,
        task_id=_TASK,
        method=QualitativeMethod.ETHNOGRAPHY,
        version=2,
        updated_at=_NOW + timedelta(minutes=1),
    )

    with Session(engine) as session:
        repository = SqliteResearchAnalysisRepository(session)
        for value in (entry, revised_entry, entry):
            repository.add_codebook_entry(value)
        for value in (theme, confirmed_theme, theme):
            repository.add_theme(value)
        for value in (profile, revised_profile, profile):
            repository.add_case_profile(value)
        for value in (cell, revised_cell, cell):
            repository.add_matrix_cell(value)
        for value in (method, revised_method, method):
            repository.add_method_selection(value)
        session.commit()

        assert (
            repository.get_codebook_entry(
                entry.code_id,
                user_id=_USER,
                task_id=_TASK,
            )
            == revised_entry
        )
        assert repository.get_theme(theme.theme_id, user_id=_USER, task_id=_TASK) == (
            confirmed_theme
        )
        assert (
            repository.get_case_profile(
                profile.profile_id,
                user_id=_USER,
                task_id=_TASK,
            )
            == revised_profile
        )
        assert repository.list_matrix_cells(user_id=_USER, task_id=_TASK) == (revised_cell,)
        assert repository.get_method_selection(user_id=_USER, task_id=_TASK) == revised_method
