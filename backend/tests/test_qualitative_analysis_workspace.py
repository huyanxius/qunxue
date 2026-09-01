from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from qunxue_api.modules.research_analysis import (
    AnalysisAnnotation,
    AnalysisAnnotationKind,
    AnalysisMemo,
    AnalysisMemoKind,
    CodebookLifecycle,
    ComparisonFindingKind,
    MatrixSubjectKind,
    MemoTargetKind,
    QualitativeMethod,
    ResearchAnalysisService,
    qualitative_method_presets,
)
from qunxue_api.modules.research_materials import MaterialLocator

_USER = UUID("10000000-0000-0000-0000-000000000186")
_TASK = UUID("20000000-0000-0000-0000-000000000186")


def _annotation(*, quote: str, case_label: str, paragraph: int) -> AnalysisAnnotation:
    return AnalysisAnnotation.create(
        user_id=_USER,
        task_id=_TASK,
        material_id=uuid4(),
        parse_id=uuid4(),
        segment_id=f"segment-{paragraph}",
        segment_content_hash=f"{paragraph:x}" * 64,
        quote=quote,
        quote_start=0,
        quote_end=len(quote),
        locator=MaterialLocator(page=1, paragraph=paragraph),
        annotation_kind=AnalysisAnnotationKind.DESCRIPTIVE,
        case_label=case_label,
        note="研究者对原文的描述性记录",
        now=datetime(2026, 8, 31, tzinfo=UTC),
    )


def _confirmed_code(
    service: ResearchAnalysisService,
    annotation: AnalysisAnnotation,
    *,
    label: str,
):
    service.add_annotation(annotation)
    return service.create_code(
        user_id=_USER,
        task_id=_TASK,
        label=label,
        definition=f"{label}的操作性定义",
        annotation_ids=(annotation.annotation_id,),
        rationale="研究者核对原文后建立",
        source="user",
        now=datetime(2026, 8, 31, tzinfo=UTC),
    )


def _confirmed_memo(
    service: ResearchAnalysisService,
    annotation: AnalysisAnnotation,
    *,
    title: str,
) -> AnalysisMemo:
    memo = AnalysisMemo.create_candidate(
        user_id=_USER,
        task_id=_TASK,
        title=title,
        content="这一解释还需要与反例一起检验。",
        memo_kind=AnalysisMemoKind.ANALYTIC,
        annotation_ids=(annotation.annotation_id,),
        source="user",
        now=datetime(2026, 8, 31, tzinfo=UTC),
    ).confirm(
        user_confirmed=True,
        expected_version=1,
        reason="研究者写入并确认",
        now=datetime(2026, 8, 31, tzinfo=UTC),
    )
    return service.add_memo(memo)


def test_codebook_revisions_keep_boundaries_examples_and_lifecycle_history() -> None:
    service = ResearchAnalysisService.in_memory()
    supporting = _annotation(
        quote="姐姐辞职后承担了全部照护。",
        case_label="家庭 A",
        paragraph=1,
    )
    counterexample = _annotation(
        quote="兄妹轮班照护，责任没有集中到一人。",
        case_label="家庭 B",
        paragraph=2,
    )
    code = _confirmed_code(service, supporting, label="照护责任集中")
    service.add_annotation(counterexample)
    merged_target = _confirmed_code(
        service,
        _annotation(
            quote="全家围绕重病成员重新安排了照护。",
            case_label="家庭 C",
            paragraph=7,
        ),
        label="照护责任重组",
    )

    entry = service.configure_codebook_entry(
        user_id=_USER,
        task_id=_TASK,
        code_id=code.code_id,
        inclusion_rules=("明确描述照护责任主要落到一人",),
        exclusion_rules=("只描述一般家务分工，没有照护责任变化",),
        positive_example_annotation_ids=(supporting.annotation_id,),
        negative_example_annotation_ids=(counterexample.annotation_id,),
        parent_code_id=None,
        expected_version=None,
    )

    assert entry.version == 1
    assert entry.lifecycle is CodebookLifecycle.ACTIVE
    assert entry.positive_example_annotation_ids == (supporting.annotation_id,)
    assert entry.negative_example_annotation_ids == (counterexample.annotation_id,)

    merged = service.transition_codebook_entry(
        user_id=_USER,
        task_id=_TASK,
        code_id=code.code_id,
        lifecycle=CodebookLifecycle.MERGED,
        related_code_ids=(merged_target.code_id,),
        expected_version=1,
        reason="并入边界更清晰的上位代码",
    )

    assert merged.version == 2
    assert merged.lifecycle is CodebookLifecycle.MERGED
    assert merged.revision_reason == "并入边界更清晰的上位代码"
    with pytest.raises(ValueError, match="stale codebook entry version"):
        service.transition_codebook_entry(
            user_id=_USER,
            task_id=_TASK,
            code_id=code.code_id,
            lifecycle=CodebookLifecycle.RETIRED,
            related_code_ids=(),
            expected_version=1,
            reason="过期写入",
        )


def test_agent_theme_remains_candidate_until_user_confirms_formal_snapshot() -> None:
    service = ResearchAnalysisService.in_memory()
    annotation = _annotation(
        quote="社区名额只通过熟人群传播。",
        case_label="社区 A",
        paragraph=3,
    )
    code = _confirmed_code(service, annotation, label="关系网络分配")

    candidate = service.create_theme(
        user_id=_USER,
        task_id=_TASK,
        label="资源可见性的分层",
        central_concept="关系网络同时决定信息可见性与资源进入机会。",
        code_ids=(code.code_id,),
        annotation_ids=(annotation.annotation_id,),
        source="agent",
        now=datetime(2026, 8, 31, tzinfo=UTC),
    )

    snapshot = service.qualitative_workspace_snapshot(user_id=_USER, task_id=_TASK)
    assert snapshot.candidate_themes == (candidate,)
    assert snapshot.formal_themes == ()
    with pytest.raises(ValueError, match="user confirmation"):
        service.confirm_theme(
            user_id=_USER,
            task_id=_TASK,
            theme_id=candidate.theme_id,
            expected_version=1,
            user_confirmed=False,
            reason="Agent 不能代替研究者确认",
        )

    confirmed = service.confirm_theme(
        user_id=_USER,
        task_id=_TASK,
        theme_id=candidate.theme_id,
        expected_version=1,
        user_confirmed=True,
        reason="研究者逐段核对后确认",
    )
    snapshot = service.qualitative_workspace_snapshot(user_id=_USER, task_id=_TASK)
    assert snapshot.candidate_themes == ()
    assert snapshot.formal_themes == (confirmed,)
    assert snapshot.schema_version == "qualitative-workspace-v1"


def test_memo_links_and_case_profiles_require_stable_source_anchors() -> None:
    service = ResearchAnalysisService.in_memory()
    annotation = _annotation(
        quote="受访者反复把补贴称为‘人情’。",
        case_label="访谈 P07",
        paragraph=4,
    )
    code = _confirmed_code(service, annotation, label="人情化表述")
    memo = _confirmed_memo(service, annotation, title="概念用词与制度经验")

    link = service.attach_memo(
        user_id=_USER,
        task_id=_TASK,
        memo_id=memo.memo_id,
        target_kind=MemoTargetKind.CODE,
        target_ref=str(code.code_id),
        annotation_ids=(annotation.annotation_id,),
    )
    profile = service.save_case_profile(
        user_id=_USER,
        task_id=_TASK,
        case_ref="case-ref-from-upstream",
        display_label="访谈 P07",
        attributes=(("代际", "青年"), ("地区", "县城")),
        summary="把正式补贴理解为关系网络中的互惠资源。",
        annotation_ids=(annotation.annotation_id,),
        memo_ids=(memo.memo_id,),
        expected_version=None,
    )

    assert link.target_kind is MemoTargetKind.CODE
    assert profile.case_ref == "case-ref-from-upstream"
    assert profile.attributes == (("代际", "青年"), ("地区", "县城"))
    with pytest.raises(ValueError, match="source annotation"):
        service.save_case_profile(
            user_id=_USER,
            task_id=_TASK,
            case_ref="case-without-source",
            display_label="没有原文的个案",
            attributes=(),
            summary="不能成为正式个案档案。",
            annotation_ids=(),
            memo_ids=(),
            expected_version=None,
        )


def test_case_theme_matrix_expands_evidence_memos_negative_cases_and_gaps() -> None:
    service = ResearchAnalysisService.in_memory()
    supporting = _annotation(
        quote="城市个案通过单位渠道很快获得了服务。",
        case_label="城市个案",
        paragraph=5,
    )
    counterexample = _annotation(
        quote="县城个案没有单位渠道，但依靠邻里获得了服务。",
        case_label="县城个案",
        paragraph=6,
    )
    code = _confirmed_code(service, supporting, label="组织渠道可及性")
    service.add_annotation(counterexample)
    memo = _confirmed_memo(service, counterexample, title="单位渠道并非必要条件")
    theme = service.create_theme(
        user_id=_USER,
        task_id=_TASK,
        label="制度资源的多重入口",
        central_concept="正式组织与非正式网络都可能构成资源入口。",
        code_ids=(code.code_id,),
        annotation_ids=(supporting.annotation_id, counterexample.annotation_id),
        source="user",
        now=datetime(2026, 8, 31, tzinfo=UTC),
    )
    profile = service.save_case_profile(
        user_id=_USER,
        task_id=_TASK,
        case_ref="case-county",
        display_label="县城个案",
        attributes=(("地区", "县城"),),
        summary="主要依靠非正式网络取得服务。",
        annotation_ids=(counterexample.annotation_id,),
        memo_ids=(memo.memo_id,),
        expected_version=None,
    )

    cell = service.save_matrix_cell(
        user_id=_USER,
        task_id=_TASK,
        case_profile_id=profile.profile_id,
        subject_kind=MatrixSubjectKind.THEME,
        subject_id=theme.theme_id,
        summary="该个案构成对‘单位渠道是必要条件’的反例。",
        annotation_ids=(counterexample.annotation_id,),
        memo_ids=(memo.memo_id,),
        finding_kinds=(
            ComparisonFindingKind.COUNTEREXAMPLE,
            ComparisonFindingKind.EVIDENCE_GAP,
        ),
        expected_version=None,
    )
    matrix = service.build_case_theme_matrix(
        user_id=_USER,
        task_id=_TASK,
        attribute_filters=(("地区", "县城"),),
    )

    assert matrix.row_profile_ids == (profile.profile_id,)
    assert matrix.cells == (cell,)
    assert matrix.cells[0].annotation_ids == (counterexample.annotation_id,)
    assert matrix.cells[0].memo_ids == (memo.memo_id,)
    assert matrix.cells[0].finding_kinds == (
        ComparisonFindingKind.COUNTEREXAMPLE,
        ComparisonFindingKind.EVIDENCE_GAP,
    )


def test_method_presets_change_views_and_prompts_without_changing_analysis_objects() -> None:
    presets = qualitative_method_presets()

    assert set(presets) == set(QualitativeMethod)
    assert presets[QualitativeMethod.THEMATIC_ANALYSIS].primary_view == "themes"
    assert "代码不等于主题" in presets[QualitativeMethod.THEMATIC_ANALYSIS].guardrails
    assert presets[QualitativeMethod.GROUNDED_THEORY].primary_view == "constant_comparison"
    assert "理论抽样" in presets[QualitativeMethod.GROUNDED_THEORY].prompts
    assert presets[QualitativeMethod.ETHNOGRAPHY].matrix_axes == ("场域", "时点")
    assert presets[QualitativeMethod.CASE_STUDY].primary_view == "case_matrix"
    assert presets[QualitativeMethod.NARRATIVE_RESEARCH].matrix_axes == ("个案", "叙事时序")
    assert presets[QualitativeMethod.DISCOURSE_CONVERSATION_ANALYSIS].primary_view == (
        "sequential_excerpt"
    )
    assert "轮次与语境" in presets[QualitativeMethod.DISCOURSE_CONVERSATION_ANALYSIS].guardrails
    assert presets[QualitativeMethod.LITERATURE_REVIEW].matrix_axes == ("文献", "概念")

    service = ResearchAnalysisService.in_memory()
    first = service.set_method_preset(
        user_id=_USER,
        task_id=_TASK,
        method=QualitativeMethod.ETHNOGRAPHY,
        expected_version=None,
    )
    second = service.set_method_preset(
        user_id=_USER,
        task_id=_TASK,
        method=QualitativeMethod.CASE_STUDY,
        expected_version=first.version,
    )
    assert second.version == 2
    assert service.snapshot(user_id=_USER, task_id=_TASK)["codes"] == ()
    assert (
        service.qualitative_workspace_snapshot(
            user_id=_USER,
            task_id=_TASK,
        ).method_preset.method
        is QualitativeMethod.CASE_STUDY
    )
