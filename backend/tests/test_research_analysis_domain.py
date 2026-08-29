from datetime import UTC, datetime
from uuid import uuid4

import pytest

from qunxue_api.modules.research_analysis import (
    AnalysisAnnotation,
    AnalysisAnnotationKind,
    AnalysisCode,
    AnalysisCodeStatus,
    AnalysisRecordStatus,
    CaseComparison,
    ComparisonFinding,
    ComparisonFindingKind,
    NextResearchStep,
    ResearchAnalysisService,
)
from qunxue_api.modules.research_materials import MaterialLocator


def _annotation(*, task_id=None, material_id=None, segment_id="segment-1"):
    quote = "参与者描述了迁移后的照护变化。"
    return AnalysisAnnotation.create(
        annotation_id=uuid4(),
        user_id=uuid4(),
        task_id=task_id or uuid4(),
        material_id=material_id or uuid4(),
        parse_id=uuid4(),
        segment_id=segment_id,
        segment_content_hash="1" * 64,
        quote=quote,
        quote_start=0,
        quote_end=len(quote),
        locator=MaterialLocator(paragraph=2),
        annotation_kind=AnalysisAnnotationKind.DESCRIPTIVE,
        case_label="案例 A",
        observed_at="2026-08-01",
        note="照护责任发生转移",
        reflection="我需要检查自己是否把家庭角色预设成固定的。",
        now=datetime.now(UTC),
    )


def test_agent_code_is_candidate_until_user_confirms() -> None:
    annotation = _annotation()
    code = AnalysisCode.candidate(
        user_id=annotation.user_id,
        task_id=annotation.task_id,
        label="照护责任重组",
        definition="迁移后照护责任在家庭成员之间重新分配。",
        annotation_ids=(annotation.annotation_id,),
        rationale="由同一片段提出的可检验候选，不是结论。",
        now=datetime.now(UTC),
        source="agent",
    )

    assert code.status is AnalysisCodeStatus.CANDIDATE
    with pytest.raises(ValueError, match="user confirmation"):
        code.confirm(
            user_confirmed=False,
            expected_version=1,
            reason="未确认",
            now=datetime.now(UTC),
        )
    with pytest.raises(ValueError, match="decision reason"):
        code.confirm(
            user_confirmed=True,
            expected_version=1,
            reason="   ",
            now=datetime.now(UTC),
        )
    confirmed = code.confirm(
        user_confirmed=True,
        expected_version=1,
        reason="研究者核对原文后确认",
        now=datetime.now(UTC),
    )
    assert confirmed.status is AnalysisCodeStatus.CONFIRMED
    assert confirmed.version == 2
    assert confirmed.decision_reason == "研究者核对原文后确认"


def test_agent_code_can_be_rejected_but_not_silently_decided_or_redecided() -> None:
    annotation = _annotation()
    code = AnalysisCode.candidate(
        user_id=annotation.user_id,
        task_id=annotation.task_id,
        label="家庭责任",
        definition="用于区分照护责任的承担方式。",
        annotation_ids=(annotation.annotation_id,),
        rationale="需要研究者判断这是否过度概括。",
        now=datetime.now(UTC),
        source="agent",
    )

    rejected = code.reject(
        user_confirmed=True,
        expected_version=1,
        reason="概念边界过宽",
        now=datetime.now(UTC),
    )

    assert rejected.status is AnalysisCodeStatus.REJECTED
    assert rejected.decision_reason == "概念边界过宽"
    assert rejected.version == 2
    with pytest.raises(ValueError, match="already decided"):
        rejected.confirm(
            user_confirmed=True,
            expected_version=2,
            reason="重复决定",
            now=datetime.now(UTC),
        )
    with pytest.raises(ValueError, match="stale"):
        code.reject(
            user_confirmed=True,
            expected_version=2,
            reason="重复决定",
            now=datetime.now(UTC),
        )


def test_annotation_keeps_description_and_reflection_as_distinct_fields() -> None:
    annotation = _annotation()
    assert annotation.annotation_kind is AnalysisAnnotationKind.DESCRIPTIVE
    assert annotation.note == "照护责任发生转移"
    assert annotation.reflection.startswith("我需要检查")


def test_researcher_reflection_requires_its_own_non_empty_reflection() -> None:
    quote = "受访者在这里停顿了。"

    with pytest.raises(ValueError, match="researcher reflection"):
        AnalysisAnnotation.create(
            user_id=uuid4(),
            task_id=uuid4(),
            material_id=uuid4(),
            parse_id=uuid4(),
            segment_id="segment-reflection",
            segment_content_hash="a" * 64,
            quote=quote,
            quote_start=0,
            quote_end=len(quote),
            locator=MaterialLocator(paragraph=4),
            annotation_kind=AnalysisAnnotationKind.RESEARCHER_REFLECTION,
            note="受访者在这里停顿。",
            reflection="   ",
            now=datetime.now(UTC),
        )


def test_annotation_keeps_exact_selection_inside_immutable_segment() -> None:
    annotation = AnalysisAnnotation.create(
        annotation_id=uuid4(),
        user_id=uuid4(),
        task_id=uuid4(),
        material_id=uuid4(),
        parse_id=uuid4(),
        segment_id="segment-1",
        segment_content_hash="0" * 64,
        quote="照护变化",
        quote_start=7,
        quote_end=11,
        locator=MaterialLocator(paragraph=2),
        annotation_kind=AnalysisAnnotationKind.DESCRIPTIVE,
        note="描述参与者对变化的叙述",
        now=datetime.now(UTC),
    )

    assert annotation.segment_content_hash == "0" * 64
    assert (annotation.quote_start, annotation.quote_end) == (7, 11)
    with pytest.raises(ValueError, match="quote range"):
        AnalysisAnnotation.create(
            user_id=annotation.user_id,
            task_id=annotation.task_id,
            material_id=annotation.material_id,
            parse_id=annotation.parse_id,
            segment_id="segment-1",
            segment_content_hash="0" * 64,
            quote="照护变化",
            quote_start=11,
            quote_end=7,
            locator=annotation.locator,
            annotation_kind=AnalysisAnnotationKind.DESCRIPTIVE,
            note="描述参与者对变化的叙述",
            now=datetime.now(UTC),
        )


def test_comparison_confirmation_requires_user_and_preserves_counter_evidence() -> None:
    comparison = CaseComparison.create(
        comparison_id=uuid4(),
        user_id=uuid4(),
        task_id=uuid4(),
        title="迁移前后照护安排比较",
        question="制度安排是否改变了照护责任？",
        case_labels=("案例 A", "案例 B"),
        time_labels=("迁移前", "迁移后"),
        findings=(
            ComparisonFinding(
                kind=ComparisonFindingKind.SUPPORT,
                statement="两案都出现照护责任重新分配。",
                annotation_ids=(uuid4(),),
            ),
            ComparisonFinding(
                kind=ComparisonFindingKind.CONTRADICT,
                statement="案例 B 中责任并未转移。",
                annotation_ids=(uuid4(),),
            ),
        ),
        competing_explanations=("家庭收入差异",),
        evidence_gaps=("缺少迁移前的照护时间记录",),
        next_steps=(
            NextResearchStep(kind="interview", action="补访案例 B 的照护安排", priority="high"),
        ),
        theory_implication="需要检验制度与家庭资源的竞争解释。",
        now=datetime.now(UTC),
        source="agent",
    )
    assert comparison.status is AnalysisRecordStatus.CANDIDATE
    with pytest.raises(ValueError, match="user confirmation"):
        comparison.confirm(
            user_confirmed=False,
            expected_version=1,
            reason="未确认",
            now=datetime.now(UTC),
        )
    confirmed = comparison.confirm(
        user_confirmed=True,
        expected_version=1,
        reason="研究者核对两个案例后确认",
        now=datetime.now(UTC),
    )
    assert confirmed.status is AnalysisRecordStatus.CONFIRMED
    assert {item.kind for item in confirmed.findings} == {
        ComparisonFindingKind.SUPPORT,
        ComparisonFindingKind.CONTRADICT,
    }


def test_service_projects_only_confirmed_analysis_into_map_patch() -> None:
    service = ResearchAnalysisService.in_memory()
    annotation = _annotation()
    service.add_annotation(annotation)
    candidate = service.create_code(
        user_id=annotation.user_id,
        task_id=annotation.task_id,
        label="照护责任重组",
        definition="责任重新分配",
        annotation_ids=(annotation.annotation_id,),
        source="agent",
    )
    assert service.research_map_patch(task_id=annotation.task_id) == {
        "nodes": [],
        "relations": [],
    }
    service.confirm_code(
        user_id=annotation.user_id,
        task_id=annotation.task_id,
        code_id=candidate.code_id,
        user_confirmed=True,
        expected_version=1,
        reason="研究者核对后确认",
    )
    patch = service.research_map_patch(task_id=annotation.task_id)
    assert any(node["kind"] == "claim" for node in patch["nodes"])
    assert all(node["status"] == "grounded" for node in patch["nodes"])


def test_comparison_preserves_every_evidence_role_and_executable_next_action() -> None:
    annotation_ids = tuple(uuid4() for _ in range(4))
    comparison = CaseComparison.create(
        user_id=uuid4(),
        task_id=uuid4(),
        title="两个社区的照护互助比较",
        question="互助网络在什么条件下能够持续？",
        case_labels=("社区甲", "社区乙"),
        time_labels=("政策前", "政策后"),
        findings=(
            ComparisonFinding(
                kind=ComparisonFindingKind.SUPPORT,
                statement="社区甲的稳定组织者支持了互助延续。",
                annotation_ids=(annotation_ids[0],),
            ),
            ComparisonFinding(
                kind=ComparisonFindingKind.COUNTEREXAMPLE,
                statement="社区乙没有稳定组织者，但互助仍持续。",
                annotation_ids=(annotation_ids[1],),
            ),
            ComparisonFinding(
                kind=ComparisonFindingKind.CONTRADICT,
                statement="同一案例的访谈与观察记录互相矛盾。",
                annotation_ids=(annotation_ids[2],),
            ),
            ComparisonFinding(
                kind=ComparisonFindingKind.COMPETING_EXPLANATION,
                statement="居住稳定性可能比组织者更能解释互助延续。",
                annotation_ids=(annotation_ids[3],),
            ),
            ComparisonFinding(
                kind=ComparisonFindingKind.EVIDENCE_GAP,
                statement="缺少政策前的连续观察。",
                annotation_ids=(),
            ),
        ),
        competing_explanations=("居住稳定性",),
        evidence_gaps=("缺少政策前的连续观察",),
        next_steps=(
            NextResearchStep(kind="interview", action="补访两地组织者", priority="high"),
            NextResearchStep(kind="observation", action="连续观察三次互助活动"),
            NextResearchStep(kind="material_collection", action="收集政策前的会议记录"),
            NextResearchStep(kind="research_question", action="追问居住稳定性如何影响互助"),
        ),
        theory_implication="组织者作用需要和居住稳定性进行竞争解释检验。",
        now=datetime.now(UTC),
    )

    assert tuple(item.kind for item in comparison.findings) == (
        ComparisonFindingKind.SUPPORT,
        ComparisonFindingKind.COUNTEREXAMPLE,
        ComparisonFindingKind.CONTRADICT,
        ComparisonFindingKind.COMPETING_EXPLANATION,
        ComparisonFindingKind.EVIDENCE_GAP,
    )
    assert tuple(item.kind for item in comparison.next_steps) == (
        "interview",
        "observation",
        "material_collection",
        "research_question",
    )
    with pytest.raises(ValueError, match="next step kind"):
        NextResearchStep(kind="write_conclusion", action="直接形成结论")


def test_declared_time_comparison_requires_two_distinct_time_anchors() -> None:
    with pytest.raises(ValueError, match="at least two time labels"):
        CaseComparison.create(
            user_id=uuid4(),
            task_id=uuid4(),
            title="单一时间点比较",
            question="时间变化是什么？",
            case_labels=("案例 A", "案例 B"),
            time_labels=("政策后",),
            findings=(
                ComparisonFinding(
                    kind=ComparisonFindingKind.SUPPORT,
                    statement="只有政策后材料。",
                    annotation_ids=(uuid4(),),
                ),
            ),
            theory_implication="当前不能形成时间比较。",
            now=datetime.now(UTC),
        )
