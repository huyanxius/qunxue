from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from qunxue_api.application.research_analysis import ResearchAnalysisApplication
from qunxue_api.modules.research_analysis import (
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
    def __init__(self, *, user_id, task_id):
        self.user_id, self.task_id = user_id, task_id

    def get(self, task_id, user_id):
        return object() if (task_id, user_id) == (self.task_id, self.user_id) else None


class _Materials:
    def __init__(self, *, material, block):
        self.material, self.block = material, block

    def get(self, material_id, *, user_id, task_id, include_deleted=False):
        if (material_id, user_id, task_id) != (
            self.material.material_id,
            self.material.user_id,
            self.material.task_id,
        ):
            return None
        return self.material

    def get_segment(self, material_id, parse_id, segment_id, *, user_id, task_id):
        if self.get(material_id, user_id=user_id, task_id=task_id) is None:
            return None
        return (
            self.block
            if (parse_id, segment_id) == (self.block.parse_id, self.block.segment_id)
            else None
        )


@pytest.fixture
def analysis_context():
    user_id, task_id, material_id, parse_id = uuid4(), uuid4(), uuid4(), uuid4()
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
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            content=text.encode(),
            material_kind=MaterialKind.INTERVIEW_TRANSCRIPT,
            now=datetime.now(UTC),
        ),
        status=MaterialStatus.READY,
        current_parse_id=parse_id,
        current_parse_version=1,
    )
    materials = _Materials(material=material, block=block)
    app = ResearchAnalysisApplication(
        analysis=ResearchAnalysisService.in_memory(),
        materials=materials,
        research_tasks=_Tasks(user_id=user_id, task_id=task_id),
    )
    return app, materials, block, user_id, task_id, []


def _confirmed_code(app, block, user_id, task_id):
    annotation = app.create_annotation(
        user_id=user_id,
        task_id=task_id,
        idempotency_key="annotation-for-code",
        material_id=block.material_id,
        parse_id=block.parse_id,
        segment_id=block.segment_id,
        quote_start=0,
        quote_end=8,
        annotation_kind="descriptive",
        note="研究者先行标记",
    )
    return app.create_user_code(
        user_id=user_id,
        task_id=task_id,
        idempotency_key="code-for-plan",
        label="照护责任分配",
        definition="家庭照护劳动在成员之间的分配方式。",
        annotation_ids=(annotation.annotation_id,),
        rationale="用户核对原文后建立",
    )


def test_agent_coding_plan_snapshots_source_and_confirmed_code(analysis_context):
    app, _materials, block, user_id, task_id, _ = analysis_context
    code = _confirmed_code(app, block, user_id, task_id)

    plan = app.propose_coding_plan_from_agent(
        user_id=user_id,
        task_id=task_id,
        title="把相邻片段归入既有代码",
        rationale="该片段延续了照护劳动如何分配的经验描述。",
        items=(
            {
                "material_id": block.material_id,
                "parse_id": block.parse_id,
                "segment_id": block.segment_id,
                "quote_start": 9,
                "quote_end": 18,
                "code_id": code.code_id,
                "confidence": 0.86,
                "rationale": "与代码定义中的照护劳动分配直接对应。",
            },
        ),
        conversation_id=uuid4(),
        agent_run_id=uuid4(),
        agent_turn_id=uuid4(),
        tool_call_id="tool-plan-1",
    )

    assert plan.status.value == "candidate"
    assert plan.items[0].quote == block.text[9:18]
    assert plan.items[0].segment_content_hash == block.content_hash
    assert plan.items[0].code_id == code.code_id
    assert plan.items[0].code_label == code.label
    assert plan.items[0].codebook_version is None


def test_user_decision_applies_existing_code_and_rejects_another_item(analysis_context):
    app, _materials, block, user_id, task_id, _ = analysis_context
    code = _confirmed_code(app, block, user_id, task_id)
    other_code = app.create_user_code(
        user_id=user_id,
        task_id=task_id,
        idempotency_key="other-code",
        label="经济支持",
        definition="经济支持作为家庭责任的一部分。",
        annotation_ids=(
            next(
                iter(app._analysis.snapshot(user_id=user_id, task_id=task_id)["annotations"])
            ).annotation_id,
        ),
        rationale="用户核对原文后建立",
    )
    plan = app.propose_coding_plan_from_agent(
        user_id=user_id,
        task_id=task_id,
        title="两条编码建议",
        rationale="需要研究者逐条确认。",
        items=(
            {
                "material_id": block.material_id,
                "parse_id": block.parse_id,
                "segment_id": block.segment_id,
                "quote_start": 9,
                "quote_end": 18,
                "code_id": code.code_id,
                "confidence": 0.86,
                "rationale": "照护分配。",
            },
            {
                "material_id": block.material_id,
                "parse_id": block.parse_id,
                "segment_id": block.segment_id,
                "quote_start": 19,
                "quote_end": len(block.text),
                "code_id": other_code.code_id,
                "confidence": 0.62,
                "rationale": "经济支持。",
            },
        ),
        conversation_id=uuid4(),
        agent_run_id=uuid4(),
        agent_turn_id=uuid4(),
        tool_call_id="tool-plan-2",
    )

    decided = app.decide_coding_plan(
        user_id=user_id,
        task_id=task_id,
        idempotency_key="decision-plan-2",
        plan_id=plan.plan_id,
        expected_version=plan.version,
        decisions=(
            (plan.items[0].item_id, "confirmed", "已回到原文核对"),
            (plan.items[1].item_id, "rejected", "证据不足，暂不采用"),
        ),
    )

    assert decided.status.value == "partially_applied"
    assert decided.items[0].status.value == "applied"
    assert decided.items[0].annotation_id is not None
    assert decided.items[1].status.value == "rejected"
    retrieved = app.retrieve_coded_segments(
        user_id=user_id,
        task_id=task_id,
        code_ids=(code.code_id,),
    )
    assert len(retrieved) == 2  # original user mark plus the newly applied segment
    assert any(item["annotation_id"] == decided.items[0].annotation_id for item in retrieved)
    assert {event.action for event in app.list_audit_events(user_id=user_id, task_id=task_id)} >= {
        "coding_plan.proposed",
        "coding_plan.decided",
        "coding_item.applied",
        "coding_item.rejected",
    }


def test_coding_plan_decision_replay_is_idempotent_and_stale_version_is_rejected(analysis_context):
    app, _materials, block, user_id, task_id, _ = analysis_context
    code = _confirmed_code(app, block, user_id, task_id)
    plan = app.propose_coding_plan_from_agent(
        user_id=user_id,
        task_id=task_id,
        title="重放测试",
        rationale="同一确认请求可能因网络重试到达两次。",
        items=(
            {
                "material_id": block.material_id,
                "parse_id": block.parse_id,
                "segment_id": block.segment_id,
                "quote_start": 9,
                "quote_end": 18,
                "code_id": code.code_id,
                "confidence": 0.8,
                "rationale": "与既有代码相符。",
            },
        ),
        conversation_id=uuid4(),
        agent_run_id=uuid4(),
        agent_turn_id=uuid4(),
        tool_call_id="tool-plan-3",
    )
    decision = ((plan.items[0].item_id, "confirmed", "已核对"),)
    first = app.decide_coding_plan(
        user_id=user_id,
        task_id=task_id,
        idempotency_key="decision-replay",
        plan_id=plan.plan_id,
        expected_version=plan.version,
        decisions=decision,
    )
    replay = app.decide_coding_plan(
        user_id=user_id,
        task_id=task_id,
        idempotency_key="decision-replay",
        plan_id=plan.plan_id,
        expected_version=plan.version,
        decisions=decision,
    )
    assert replay == first
    with pytest.raises(ValueError, match="stale"):
        app.decide_coding_plan(
            user_id=user_id,
            task_id=task_id,
            idempotency_key="decision-stale",
            plan_id=plan.plan_id,
            expected_version=plan.version,
            decisions=decision,
        )


def test_coding_plan_rejects_source_hash_drift(analysis_context):
    app, materials, block, user_id, task_id, _ = analysis_context
    code = _confirmed_code(app, block, user_id, task_id)
    plan = app.propose_coding_plan_from_agent(
        user_id=user_id,
        task_id=task_id,
        title="漂移测试",
        rationale="需要保护来源锚点。",
        items=(
            {
                "material_id": block.material_id,
                "parse_id": block.parse_id,
                "segment_id": block.segment_id,
                "quote_start": 9,
                "quote_end": 18,
                "code_id": code.code_id,
                "confidence": 0.8,
                "rationale": "待核对。",
            },
        ),
        conversation_id=uuid4(),
        agent_run_id=uuid4(),
        agent_turn_id=uuid4(),
        tool_call_id="tool-plan-4",
    )
    materials.block = replace(block, text=block.text + "来源已重解析", content_hash="f" * 64)
    with pytest.raises(ValueError, match="source"):
        app.decide_coding_plan(
            user_id=user_id,
            task_id=task_id,
            idempotency_key="decision-drift",
            plan_id=plan.plan_id,
            expected_version=plan.version,
            decisions=((plan.items[0].item_id, "confirmed", "核对"),),
        )


def test_user_can_revoke_an_applied_plan_without_removing_the_original_code(analysis_context):
    app, _materials, block, user_id, task_id, _ = analysis_context
    code = _confirmed_code(app, block, user_id, task_id)
    plan = app.propose_coding_plan_from_agent(
        user_id=user_id,
        task_id=task_id,
        title="可撤销计划",
        rationale="验证撤销闭环。",
        items=(
            {
                "material_id": block.material_id,
                "parse_id": block.parse_id,
                "segment_id": block.segment_id,
                "quote_start": 9,
                "quote_end": 18,
                "code_id": code.code_id,
                "confidence": 0.8,
                "rationale": "待核对。",
            },
        ),
        conversation_id=uuid4(),
        agent_run_id=uuid4(),
        agent_turn_id=uuid4(),
        tool_call_id="tool-plan-revoke",
    )
    applied = app.decide_coding_plan(
        user_id=user_id,
        task_id=task_id,
        idempotency_key="decision-revoke",
        plan_id=plan.plan_id,
        expected_version=plan.version,
        decisions=((plan.items[0].item_id, "confirmed", "已核对"),),
    )

    revoked = app.revoke_coding_plan(
        user_id=user_id,
        task_id=task_id,
        idempotency_key="revoke-plan",
        plan_id=plan.plan_id,
        expected_version=applied.version,
        reason="误点确认，撤回本批次",
    )

    assert revoked.status.value == "revoked"
    assert revoked.items[0].status.value == "revoked"
    assert (
        len(app.retrieve_coded_segments(user_id=user_id, task_id=task_id, code_ids=(code.code_id,)))
        == 1
    )
    assert "coding_plan.revoked" in {
        event.action for event in app.list_audit_events(user_id=user_id, task_id=task_id)
    }
