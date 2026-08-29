from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from qunxue_api.application.research_analysis import ResearchAnalysisApplication
from qunxue_api.modules.research_analysis import (
    AnalysisAnnotationKind,
    AnalysisCodeStatus,
    AnalysisMemoKind,
    AnalysisRecordStatus,
    ComparisonFinding,
    ComparisonFindingKind,
    NextResearchStep,
    ResearchAnalysisIdempotencyConflict,
    ResearchAnalysisService,
)
from qunxue_api.modules.research_materials import (
    MaterialBlock,
    MaterialKind,
    MaterialLocator,
    MaterialStatus,
    ResearchMaterial,
)


class _Tasks:
    def __init__(self, *, user_id, task_id) -> None:
        self.user_id = user_id
        self.task_id = task_id

    def get(self, task_id, user_id):
        return object() if (task_id, user_id) == (self.task_id, self.user_id) else None


class _Materials:
    def __init__(self, *, material, block) -> None:
        self.material = material
        self.block = block
        self.deleted = False

    def get(self, material_id, *, user_id, task_id, include_deleted=False):
        if (
            material_id != self.material.material_id
            or user_id != self.material.user_id
            or task_id != self.material.task_id
            or (self.deleted and not include_deleted)
        ):
            return None
        return replace(
            self.material,
            status=MaterialStatus.DELETED if self.deleted else self.material.status,
        )

    def get_segment(
        self,
        material_id,
        parse_id,
        segment_id,
        *,
        user_id,
        task_id,
    ):
        if (
            self.get(
                material_id,
                user_id=user_id,
                task_id=task_id,
            )
            is None
        ):
            return None
        if (parse_id, segment_id) != (self.block.parse_id, self.block.segment_id):
            return None
        return self.block


class _MaterialSet:
    def __init__(self, *, materials, blocks) -> None:
        self.materials = {item.material_id: item for item in materials}
        self.blocks = {
            (item.material_id, item.parse_id, item.segment_id): item for item in blocks
        }
        self.deleted: set = set()

    def get(self, material_id, *, user_id, task_id, include_deleted=False):
        material = self.materials.get(material_id)
        if (
            material is None
            or material.user_id != user_id
            or material.task_id != task_id
            or (material_id in self.deleted and not include_deleted)
        ):
            return None
        return replace(
            material,
            status=(
                MaterialStatus.DELETED
                if material_id in self.deleted
                else material.status
            ),
        )

    def get_segment(
        self,
        material_id,
        parse_id,
        segment_id,
        *,
        user_id,
        task_id,
    ):
        if self.get(material_id, user_id=user_id, task_id=task_id) is None:
            return None
        return self.blocks.get((material_id, parse_id, segment_id))


@pytest.fixture
def analysis_context():
    user_id = uuid4()
    task_id = uuid4()
    material_id = uuid4()
    parse_id = uuid4()
    text = "迁移以后，姐姐承担了大部分照护，弟弟主要提供经济支持。"
    block = MaterialBlock.create(
        material_id=material_id,
        parse_id=parse_id,
        ordinal=0,
        kind="paragraph",
        text=text,
        locator=MaterialLocator(section_path=("家庭安排",), paragraph=3),
    )
    material = replace(
        ResearchMaterial.create(
            material_id=material_id,
            user_id=user_id,
            task_id=task_id,
            idempotency_key="upload-1",
            original_filename="访谈 A.docx",
            media_type=("application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
            content=b"docx",
            material_kind=MaterialKind.INTERVIEW_TRANSCRIPT,
            now=datetime.now(UTC),
        ),
        status=MaterialStatus.READY,
        current_parse_id=parse_id,
        current_parse_version=1,
    )
    materials = _Materials(material=material, block=block)
    commits: list[bool] = []
    app = ResearchAnalysisApplication(
        analysis=ResearchAnalysisService.in_memory(),
        materials=materials,
        research_tasks=_Tasks(user_id=user_id, task_id=task_id),
        commit=lambda: commits.append(True),
    )
    return app, materials, block, user_id, task_id, commits


@pytest.fixture
def comparison_context():
    user_id = uuid4()
    task_id = uuid4()
    cases = (
        ("家庭 A", "迁移前", "母亲和姐姐共同照护，责任分配相对平均。"),
        ("家庭 B", "迁移后", "兄弟共同承担照护，并由邻里网络补位。"),
    )
    blocks = []
    materials = []
    for index, (_case_label, _observed_at, text) in enumerate(cases, start=1):
        material_id = uuid4()
        parse_id = uuid4()
        block = MaterialBlock.create(
            material_id=material_id,
            parse_id=parse_id,
            ordinal=0,
            kind="paragraph",
            text=text,
            locator=MaterialLocator(section_path=(f"访谈 {index}",), paragraph=1),
        )
        material = replace(
            ResearchMaterial.create(
                material_id=material_id,
                user_id=user_id,
                task_id=task_id,
                idempotency_key=f"comparison-upload-{index}",
                original_filename=f"访谈 {index}.txt",
                media_type="text/plain",
                content=text.encode(),
                material_kind=MaterialKind.INTERVIEW_TRANSCRIPT,
                now=datetime.now(UTC),
            ),
            status=MaterialStatus.READY,
            current_parse_id=parse_id,
            current_parse_version=1,
        )
        blocks.append(block)
        materials.append(material)
    reader = _MaterialSet(materials=materials, blocks=blocks)
    service = ResearchAnalysisService.in_memory()
    commits: list[bool] = []
    app = ResearchAnalysisApplication(
        analysis=service,
        materials=reader,
        research_tasks=_Tasks(user_id=user_id, task_id=task_id),
        commit=lambda: commits.append(True),
    )
    return app, service, reader, tuple(blocks), cases, user_id, task_id, commits


def _annotate_comparison_cases(context):
    app, _, _, blocks, cases, user_id, task_id, _ = context
    annotations = []
    for index, (block, (case_label, observed_at, text)) in enumerate(
        zip(blocks, cases, strict=True),
        start=1,
    ):
        annotations.append(
            app.create_annotation(
                user_id=user_id,
                task_id=task_id,
                idempotency_key=f"comparison-annotation-{index}",
                material_id=block.material_id,
                parse_id=block.parse_id,
                segment_id=block.segment_id,
                quote_start=0,
                quote_end=len(text),
                annotation_kind=AnalysisAnnotationKind.DESCRIPTIVE,
                note=f"{case_label} 的照护安排",
                case_label=case_label,
                observed_at=observed_at,
            )
        )
    return tuple(annotations)


def _annotate(context, *, idempotency_key="annotation-request-1"):
    app, _, block, user_id, task_id, _ = context
    quote = "姐姐承担了大部分照护"
    start = block.text.index(quote)
    return app.create_annotation(
        user_id=user_id,
        task_id=task_id,
        idempotency_key=idempotency_key,
        material_id=block.material_id,
        parse_id=block.parse_id,
        segment_id=block.segment_id,
        quote_start=start,
        quote_end=start + len(quote),
        annotation_kind=AnalysisAnnotationKind.DESCRIPTIVE,
        note="照护责任集中到姐姐",
        reflection="需要避免把性别分工当作先验解释。",
        case_label="家庭 A",
        observed_at="迁移后",
    )


def test_annotation_is_derived_from_owned_immutable_segment(analysis_context) -> None:
    app, _, block, user_id, task_id, commits = analysis_context

    annotation = _annotate(analysis_context)

    assert annotation.quote == "姐姐承担了大部分照护"
    assert annotation.segment_content_hash == block.content_hash
    assert annotation.locator == block.locator
    assert annotation.note == "照护责任集中到姐姐"
    assert annotation.reflection == "需要避免把性别分工当作先验解释。"
    assert commits == [True]
    with pytest.raises(Exception, match="Research task"):
        app.create_annotation(
            user_id=uuid4(),
            task_id=task_id,
            idempotency_key="annotation-wrong-owner",
            material_id=block.material_id,
            parse_id=block.parse_id,
            segment_id=block.segment_id,
            quote_start=0,
            quote_end=2,
            annotation_kind=AnalysisAnnotationKind.DESCRIPTIVE,
            note="越权片段",
        )
    with pytest.raises(ValueError, match="selection"):
        app.create_annotation(
            user_id=user_id,
            task_id=task_id,
            idempotency_key="annotation-outside-selection",
            material_id=block.material_id,
            parse_id=block.parse_id,
            segment_id=block.segment_id,
            quote_start=999,
            quote_end=1000,
            annotation_kind=AnalysisAnnotationKind.DESCRIPTIVE,
            note="不存在的选区",
        )


def test_agent_analysis_stays_candidate_until_user_decides(analysis_context) -> None:
    app, _, _, user_id, task_id, _ = analysis_context
    annotation = _annotate(analysis_context)

    candidate = app.propose_code_from_agent(
        user_id=user_id,
        task_id=task_id,
        label="照护责任性别化",
        definition="照护劳动按性别集中分配。",
        annotation_ids=(annotation.annotation_id,),
        rationale="该片段支持候选编码，但需要跨案例核对。",
        conversation_id=uuid4(),
        agent_run_id=uuid4(),
        agent_turn_id=uuid4(),
        tool_call_id="call-analysis-candidate",
    )

    assert candidate.status is AnalysisCodeStatus.CANDIDATE
    confirmed = app.decide_code(
        user_id=user_id,
        task_id=task_id,
        code_id=candidate.code_id,
        expected_version=1,
        decision=AnalysisCodeStatus.CONFIRMED,
        reason="已核对原文，保留为分析编码",
    )
    assert confirmed.status is AnalysisCodeStatus.CONFIRMED
    assert confirmed.version == 2
    with pytest.raises(ValueError, match="stale|already decided"):
        app.decide_code(
            user_id=user_id,
            task_id=task_id,
            code_id=candidate.code_id,
            expected_version=1,
            decision=AnalysisCodeStatus.REJECTED,
            reason="重复决定",
        )


def test_user_write_idempotency_replays_and_rejects_cross_operation_reuse(
    analysis_context,
) -> None:
    app, _, _, user_id, task_id, commits = analysis_context

    first = _annotate(analysis_context, idempotency_key="same-analysis-write")
    replay = _annotate(analysis_context, idempotency_key="same-analysis-write")

    assert replay == first
    assert commits == [True, True]
    with pytest.raises(ResearchAnalysisIdempotencyConflict):
        app.create_user_code(
            user_id=user_id,
            task_id=task_id,
            idempotency_key="same-analysis-write",
            label="照护责任性别化",
            definition="照护劳动按性别集中分配。",
            annotation_ids=(first.annotation_id,),
            rationale="研究者核对原文后建立。",
        )


def test_invalid_annotation_does_not_consume_its_idempotency_key(
    analysis_context,
) -> None:
    app, _, block, user_id, task_id, _ = analysis_context
    quote = "姐姐承担了大部分照护"
    start = block.text.index(quote)
    payload = {
        "user_id": user_id,
        "task_id": task_id,
        "idempotency_key": "repair-reflection-request",
        "material_id": block.material_id,
        "parse_id": block.parse_id,
        "segment_id": block.segment_id,
        "quote_start": start,
        "quote_end": start + len(quote),
        "annotation_kind": AnalysisAnnotationKind.RESEARCHER_REFLECTION,
        "note": "受访者描述照护责任集中。",
    }

    with pytest.raises(ValueError, match="researcher reflection"):
        app.create_annotation(**payload, reflection="   ")

    created = app.create_annotation(**payload, reflection="我需要检查性别预设。")
    assert created.reflection == "我需要检查性别预设。"


def test_invalid_user_code_does_not_consume_its_idempotency_key(
    analysis_context,
) -> None:
    app, _, _, user_id, task_id, _ = analysis_context
    annotation = _annotate(analysis_context)
    payload = {
        "user_id": user_id,
        "task_id": task_id,
        "idempotency_key": "repair-user-code",
        "definition": "照护劳动按性别集中分配。",
        "annotation_ids": (annotation.annotation_id,),
        "rationale": "研究者核对原文后建立。",
    }

    with pytest.raises(ValueError, match="code label"):
        app.create_user_code(**payload, label="   ")

    created = app.create_user_code(**payload, label="照护责任性别化")
    assert created.status is AnalysisCodeStatus.CONFIRMED


def test_invalid_user_memo_does_not_consume_its_idempotency_key(
    analysis_context,
) -> None:
    app, _, _, user_id, task_id, _ = analysis_context
    payload = {
        "user_id": user_id,
        "task_id": task_id,
        "idempotency_key": "repair-user-memo",
        "title": "替代解释待检验",
        "memo_kind": AnalysisMemoKind.ANALYTIC,
    }

    with pytest.raises(ValueError, match="memo content"):
        app.create_user_memo(**payload, content="   ")

    created = app.create_user_memo(
        **payload,
        content="经济资源差异也可能解释责任分配。",
    )
    assert created.status is AnalysisRecordStatus.CONFIRMED


def test_agent_proposals_keep_provenance_and_replay_the_same_tool_call(
    analysis_context,
) -> None:
    app, _, _, user_id, task_id, _ = analysis_context
    annotation = _annotate(analysis_context)
    provenance = {
        "conversation_id": uuid4(),
        "agent_run_id": uuid4(),
        "agent_turn_id": uuid4(),
        "tool_call_id": "call-analysis-code-1",
    }

    code = app.propose_code_from_agent(
        user_id=user_id,
        task_id=task_id,
        label="照护责任性别化",
        definition="照护劳动按性别集中分配。",
        annotation_ids=(annotation.annotation_id,),
        rationale="需要跨材料复核。",
        **provenance,
    )
    replay = app.propose_code_from_agent(
        user_id=user_id,
        task_id=task_id,
        label="照护责任性别化",
        definition="照护劳动按性别集中分配。",
        annotation_ids=(annotation.annotation_id,),
        rationale="需要跨材料复核。",
        **provenance,
    )

    assert replay == code
    assert code.status is AnalysisCodeStatus.CANDIDATE
    assert code.conversation_id == provenance["conversation_id"]
    assert code.agent_run_id == provenance["agent_run_id"]
    assert code.agent_turn_id == provenance["agent_turn_id"]
    assert code.tool_call_id == provenance["tool_call_id"]

    memo = app.propose_memo_from_agent(
        user_id=user_id,
        task_id=task_id,
        title="替代解释待检验",
        content="经济资源差异也可能解释责任分配。",
        memo_kind="analytic",
        annotation_ids=(annotation.annotation_id,),
        code_ids=(code.code_id,),
        conversation_id=provenance["conversation_id"],
        agent_run_id=provenance["agent_run_id"],
        agent_turn_id=provenance["agent_turn_id"],
        tool_call_id="call-analysis-memo-1",
    )
    assert memo.status is AnalysisRecordStatus.CANDIDATE
    assert memo.tool_call_id == "call-analysis-memo-1"

    with pytest.raises(ResearchAnalysisIdempotencyConflict):
        app.propose_code_from_agent(
            user_id=user_id,
            task_id=task_id,
            label="另一个编码",
            definition="同一工具调用不得改写。",
            annotation_ids=(annotation.annotation_id,),
            rationale="这是不同载荷。",
            **provenance,
        )


def test_agent_comparison_is_idempotent_candidate_with_complete_provenance(
    comparison_context,
) -> None:
    app, _, _, _, _, user_id, task_id, _ = comparison_context
    annotation_a, annotation_b = _annotate_comparison_cases(comparison_context)
    provenance = {
        "conversation_id": uuid4(),
        "agent_run_id": uuid4(),
        "agent_turn_id": uuid4(),
        "tool_call_id": "call-case-comparison-1",
    }
    payload = {
        "user_id": user_id,
        "task_id": task_id,
        "title": "迁移前后两个家庭的照护安排",
        "question": "迁移是否必然强化性别化照护？",
        "case_labels": ("家庭 A", "家庭 B"),
        "time_labels": ("迁移前", "迁移后"),
        "findings": (
            ComparisonFinding(
                kind=ComparisonFindingKind.SUPPORT,
                statement="家庭 A 的照护仍集中于女性。",
                annotation_ids=(annotation_a.annotation_id,),
            ),
            ComparisonFinding(
                kind=ComparisonFindingKind.COUNTEREXAMPLE,
                statement="家庭 B 的兄弟共同承担照护。",
                annotation_ids=(annotation_b.annotation_id,),
            ),
            ComparisonFinding(
                kind=ComparisonFindingKind.COMPETING_EXPLANATION,
                statement="邻里网络可能比迁移本身更能解释责任变化。",
                annotation_ids=(annotation_b.annotation_id,),
            ),
            ComparisonFinding(
                kind=ComparisonFindingKind.EVIDENCE_GAP,
                statement="缺少家庭 B 迁移前的连续记录。",
                annotation_ids=(),
            ),
        ),
        "competing_explanations": ("邻里互助网络",),
        "evidence_gaps": ("缺少家庭 B 迁移前的连续记录",),
        "next_steps": (
            NextResearchStep(
                kind="interview",
                action="补访家庭 B 的迁移前照护安排",
                priority="high",
            ),
        ),
        "theory_implication": "性别分工解释需要与邻里网络解释竞争检验。",
        **provenance,
    }

    candidate = app.propose_comparison_from_agent(**payload)
    replay = app.propose_comparison_from_agent(**payload)

    assert replay == candidate
    assert candidate.status is AnalysisRecordStatus.CANDIDATE
    assert candidate.version == 1
    assert candidate.conversation_id == provenance["conversation_id"]
    assert candidate.agent_run_id == provenance["agent_run_id"]
    assert candidate.agent_turn_id == provenance["agent_turn_id"]
    assert candidate.tool_call_id == provenance["tool_call_id"]
    with pytest.raises(ResearchAnalysisIdempotencyConflict):
        app.propose_comparison_from_agent(
            **{**payload, "question": "同一工具调用不得改变问题"}
        )

    confirmed = app.decide_comparison(
        user_id=user_id,
        task_id=task_id,
        comparison_id=candidate.comparison_id,
        expected_version=1,
        decision=AnalysisRecordStatus.CONFIRMED,
        reason="研究者核对两个案例与原文后确认",
    )
    assert confirmed.status is AnalysisRecordStatus.CONFIRMED
    assert confirmed.version == 2
    assert confirmed.decision_reason == "研究者核对两个案例与原文后确认"
    with pytest.raises(ValueError, match="stale|already decided"):
        app.decide_comparison(
            user_id=user_id,
            task_id=task_id,
            comparison_id=candidate.comparison_id,
            expected_version=1,
            decision=AnalysisRecordStatus.REJECTED,
            reason="重复决定",
        )


def test_user_comparison_replays_idempotently_and_requires_real_anchors(
    comparison_context,
) -> None:
    app, _, _, _, _, user_id, task_id, _ = comparison_context
    annotation_a, annotation_b = _annotate_comparison_cases(comparison_context)
    payload = {
        "user_id": user_id,
        "task_id": task_id,
        "idempotency_key": "user-comparison-1",
        "title": "两个家庭的照护差异",
        "question": "照护责任如何随迁移改变？",
        "case_labels": ("家庭 A", "家庭 B"),
        "time_labels": ("迁移前", "迁移后"),
        "findings": (
            ComparisonFinding(
                kind=ComparisonFindingKind.SUPPORT,
                statement="两个家庭都出现责任重新协商。",
                annotation_ids=(annotation_a.annotation_id, annotation_b.annotation_id),
            ),
        ),
        "theory_implication": "迁移影响取决于可用的家庭外支持。",
    }
    first = app.create_user_comparison(**payload)
    replay = app.create_user_comparison(**payload)
    assert replay == first
    assert first.status is AnalysisRecordStatus.CONFIRMED

    with pytest.raises(ValueError, match="two materials"):
        app.create_user_comparison(
            **{
                **payload,
                "idempotency_key": "single-material-comparison",
                "findings": (
                    ComparisonFinding(
                        kind=ComparisonFindingKind.SUPPORT,
                        statement="只引用了一个材料。",
                        annotation_ids=(annotation_a.annotation_id,),
                    ),
                ),
            }
        )


def test_confirmed_projection_excludes_candidate_and_rejected_comparisons(
    comparison_context,
) -> None:
    app, _, _, _, _, user_id, task_id, _ = comparison_context
    annotation_a, annotation_b = _annotate_comparison_cases(comparison_context)
    base = {
        "user_id": user_id,
        "task_id": task_id,
        "case_labels": ("家庭 A", "家庭 B"),
        "time_labels": ("迁移前", "迁移后"),
        "findings": (
            ComparisonFinding(
                kind=ComparisonFindingKind.SUPPORT,
                statement="家庭外支持改变了照护协商空间。",
                annotation_ids=(annotation_a.annotation_id, annotation_b.annotation_id),
            ),
            ComparisonFinding(
                kind=ComparisonFindingKind.EVIDENCE_GAP,
                statement="缺少长期跟踪。",
                annotation_ids=(),
            ),
        ),
        "evidence_gaps": ("缺少长期跟踪",),
        "next_steps": (
            NextResearchStep(kind="observation", action="继续观察六个月"),
        ),
        "theory_implication": "家庭外支持是迁移影响照护分工的条件。",
    }
    confirmed = app.create_user_comparison(
        **base,
        idempotency_key="confirmed-comparison",
        title="已确认比较",
        question="家庭外支持有什么作用？",
    )
    candidate = app.propose_comparison_from_agent(
        **base,
        title="候选比较",
        question="候选问题",
        conversation_id=uuid4(),
        agent_run_id=uuid4(),
        agent_turn_id=uuid4(),
        tool_call_id="candidate-comparison",
    )
    rejected_candidate = app.propose_comparison_from_agent(
        **base,
        title="被拒绝比较",
        question="被拒绝问题",
        conversation_id=uuid4(),
        agent_run_id=uuid4(),
        agent_turn_id=uuid4(),
        tool_call_id="rejected-comparison",
    )
    rejected = app.decide_comparison(
        user_id=user_id,
        task_id=task_id,
        comparison_id=rejected_candidate.comparison_id,
        expected_version=1,
        decision=AnalysisRecordStatus.REJECTED,
        reason="研究者认为两案不可直接比较",
    )

    projection = app.get_confirmed_comparison_projection(
        user_id=user_id,
        task_id=task_id,
    )

    assert tuple(item.comparison_id for item in projection.comparisons) == (
        confirmed.comparison_id,
    )
    assert candidate.comparison_id not in {
        item.comparison_id for item in projection.comparisons
    }
    assert rejected.comparison_id not in {
        item.comparison_id for item in projection.comparisons
    }
    assert {item.finding_kind for item in projection.evidence_items} == {
        ComparisonFindingKind.SUPPORT,
    }
    assert any(
        node["id"] == f"analysis-comparison:{confirmed.comparison_id}"
        for node in projection.research_map_patch["nodes"]
    )
    assert not any(
        str(candidate.comparison_id) in str(node)
        or str(rejected.comparison_id) in str(node)
        for node in projection.research_map_patch["nodes"]
    )


def test_confirmed_memo_and_case_comparison_form_a_traceable_handoff(
    comparison_context,
) -> None:
    app, _, materials, _, _, user_id, task_id, _ = comparison_context
    annotation, second_annotation = _annotate_comparison_cases(comparison_context)
    code = app.create_user_code(
        user_id=user_id,
        task_id=task_id,
        idempotency_key="user-code-1",
        label="照护责任性别化",
        definition="照护劳动按性别集中分配。",
        annotation_ids=(annotation.annotation_id,),
        rationale="研究者核对原文后建立。",
    )
    memo = app.create_user_memo(
        user_id=user_id,
        task_id=task_id,
        idempotency_key="user-memo-1",
        title="性别分工并非唯一解释",
        content="经济资源差异也可能解释家庭内责任安排。",
        memo_kind=AnalysisMemoKind.ANALYTIC,
        annotation_ids=(annotation.annotation_id,),
        code_ids=(code.code_id,),
    )
    comparison = app.create_user_comparison(
        user_id=user_id,
        task_id=task_id,
        idempotency_key="user-comparison-handoff-1",
        title="家庭 A 与家庭 B 的照护安排",
        question="迁移是否总会强化照护责任的性别分化？",
        case_labels=("家庭 A", "家庭 B"),
        time_labels=("迁移前", "迁移后"),
        findings=(
            ComparisonFinding(
                kind=ComparisonFindingKind.SUPPORT,
                statement="家庭 A 中姐姐承担主要照护。",
                annotation_ids=(annotation.annotation_id,),
            ),
            ComparisonFinding(
                kind=ComparisonFindingKind.COUNTEREXAMPLE,
                statement="家庭 B 的兄弟共同承担照护。",
                annotation_ids=(second_annotation.annotation_id,),
            ),
        ),
        competing_explanations=("家庭收入结构",),
        evidence_gaps=("家庭 B 缺少迁移前记录",),
        next_steps=(
            NextResearchStep(
                kind="interview",
                action="补访家庭 B 的迁移前照护安排",
                priority="high",
            ),
        ),
        theory_implication="性别分工解释需要与资源差异解释竞争检验。",
    )

    assert memo.status is AnalysisRecordStatus.CONFIRMED
    assert comparison.status is AnalysisRecordStatus.CONFIRMED
    handoff = app.formal_handoff(user_id=user_id, task_id=task_id)
    assert handoff.content_hash
    assert tuple(item.code_id for item in handoff.codes) == (code.code_id,)
    assert tuple(item.memo_id for item in handoff.memos) == (memo.memo_id,)
    assert tuple(item.comparison_id for item in handoff.comparisons) == (comparison.comparison_id,)
    assert handoff.unavailable_annotation_ids == ()

    materials.deleted.add(annotation.material_id)
    deleted_handoff = app.formal_handoff(user_id=user_id, task_id=task_id)
    assert tuple(item.annotation_id for item in deleted_handoff.annotations) == (
        second_annotation.annotation_id,
    )
    assert deleted_handoff.unavailable_annotation_ids == (annotation.annotation_id,)

    snapshot = app.list_snapshot(user_id=user_id, task_id=task_id)
    tombstone = next(
        item for item in snapshot["annotations"] if item.annotation_id == annotation.annotation_id
    )
    assert tombstone.quote == ""
    assert tombstone.quote_hash == annotation.quote_hash
    assert tombstone.locator == annotation.locator
    assert tombstone.source_available is False
    assert tombstone.unavailable_reason == "source_deleted"

    agent_snapshot = app.get_for_agent(user_id=user_id, task_id=task_id)
    agent_tombstone = next(
        item
        for item in agent_snapshot["annotations"]
        if item.annotation_id == annotation.annotation_id
    )
    assert agent_tombstone.quote == ""
