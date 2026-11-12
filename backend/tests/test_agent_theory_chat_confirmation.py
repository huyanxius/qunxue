import json
from copy import deepcopy
from uuid import UUID

import pytest
from pydantic_ai.models.function import DeltaToolCall, FunctionModel
from test_research_document_agent_tools import _install_pre_reviewed_release

from qunxue_api.adapters.research_agent.pydantic_runner import PydanticAIKnowledgeRunner


@pytest.fixture
def research_chat(client):
    registered = client.post(
        "/api/session/register",
        json={"email": "chat-plan@example.com", "password": "research-pass-123"},
        headers={"Idempotency-Key": "register-chat-plan"},
    )
    assert registered.status_code == 201
    user_id = UUID(registered.json()["user"]["user_id"])
    _install_pre_reviewed_release(client)
    with client.app.state.disciplinary_agent_scope() as application:
        turn = application.run_turn(
            user_id=user_id,
            conversation_id=None,
            prompt="建立关于社区互助的研究",
            idempotency_key="chat-plan-start",
            workspace="research",
        )
        conversation_id = turn.conversation.conversation_id
        tools = application._tools_factory()
        tools.bind_agent_context(
            user_id=user_id, conversation_id=conversation_id,
            agent_run_id=turn.run_id, agent_turn_id=turn.turn.turn_id,
        )
        proposal = tools.propose_start_research(
            phenomenon="社区成员流动正在改变邻里互助",
            research_intent="解释互助关系变化的机制", context="城市社区",
        )
        tools.finalize_agent_turn(source_turn_id=turn.turn.turn_id)
    confirmed = client.post(
        f"/api/agent/research-start-proposals/{proposal['proposal_id']}/confirm",
        headers={"Idempotency-Key": "chat-plan-start-confirm"},
        json={
            "expected_version": proposal["version"],
            "phenomenon": proposal["phenomenon"],
            "research_intent": proposal["research_intent"], "context": proposal["context"],
        },
    )
    assert confirmed.status_code == 201
    with client.app.state.disciplinary_agent_scope() as application:
        tools = application._tools_factory()
        tools.bind_agent_context(
            user_id=user_id, conversation_id=conversation_id, agent_run_id=turn.run_id,
        )
        matched = tools.start_theory_matching()
    candidates = matched["candidates"]
    payload = {
        "decisions": [
            {
                "candidate_id": item["candidate_id"],
                "action": "adopt" if index == 0 else "exclude",
                "reason": "作为主要解释视角" if index == 0 else "本版暂不采用",
                "related_source_ids": item["source_ids"],
            }
            for index, item in enumerate(candidates)
        ],
        "use_assignments": [{
            "candidate_id": candidates[0]["candidate_id"], "role_code": "primary",
            "responsibility": "解释社区流动与互助变化的机制",
        }],
        "relations": [],
    }
    return client, user_id, conversation_id, payload


def chat_turn(chat, *, prompt, calls, key, interrupted=False):
    client, user_id, conversation_id, _ = chat
    pending = list(calls)
    called_tools = {name for name, _ in calls}
    outputs = []

    async def model_stream(_messages, _info):
        if interrupted:
            raise RuntimeError("synthetic interrupted response")
        if pending:
            name, payload = pending.pop(0)
            if callable(payload):
                payload = payload(outputs)
            yield {0: DeltaToolCall(name=name, json_args=json.dumps(payload), tool_call_id=name)}
        else:
            yield "请核对下面的理论方案；同意后在聊天里确认。"

    runner = PydanticAIKnowledgeRunner(
        base_url="https://model.example.invalid/v1", api_key="test-key",
        model="test-model", timeout_seconds=1,
    )
    deltas = []
    with (
        client.app.state.disciplinary_agent_scope() as application,
        runner._agent.override(model=FunctionModel(stream_function=model_stream)),
    ):
        application._runner = runner
        execution = application.run_turn(
            user_id=user_id, conversation_id=conversation_id, prompt=prompt,
            idempotency_key=key, workspace="research", on_delta=deltas.append,
            on_tool_event=lambda event: outputs.append(event.output)
            if event.phase == "finished" and event.tool in called_tools else None,
        )
    return execution, outputs, "".join(deltas)


def save_payload(proposal, payload):
    return {"plan_id": proposal["plan_id"], "content_hash": proposal["content_hash"], **payload}


def test_chat_confirmation_saves_only_the_displayed_plan_in_a_later_user_turn(research_chat):
    client, user_id, conversation_id, payload = research_chat
    displayed, proposals, streamed = chat_turn(
        research_chat, prompt="请提出理论方案", calls=[("propose_theory_plan", payload)],
        key="display-plan",
    )
    assert proposals and proposals[0]["status"] == "draft"
    assert "解释社区流动与互助变化的机制" in displayed.result.answer
    assert streamed == displayed.result.answer
    with client.app.state.disciplinary_agent_scope() as application:
        assert application._tools_factory()._workflow.get_state(
            user_id=user_id, conversation_id=conversation_id,
        )["theory_plan_id"] is None
    _, saved, _ = chat_turn(
        research_chat, prompt="确认",
        calls=[
            ("get_research_workflow_state", {}),
            ("save_confirmed_theory_plan", lambda outputs: save_payload(
                outputs[-1]["pending_theory_plan"], outputs[-1]["pending_theory_plan"]["content"],
            )),
        ],
        key="confirm-displayed-plan",
    )
    assert saved[-1]["status"] == "confirmed"
    plan = client.get(f"/api/theory-plans/{saved[-1]['theory_plan_id']}")
    assert plan.status_code == 200
    assert plan.json()["use_assignments"][0]["responsibility"] == (
        "解释社区流动与互助变化的机制"
    )


@pytest.mark.parametrize("prompt", ["先给我看看方案", "确认"])
def test_proposing_and_saving_in_one_turn_stays_a_draft(research_chat, prompt):
    _, outputs, _ = chat_turn(
        research_chat, prompt=prompt,
        calls=[
            ("propose_theory_plan", research_chat[3]),
            ("save_confirmed_theory_plan", lambda outputs: save_payload(
                outputs[0], research_chat[3],
            )),
        ], key="no-later-user-message",
    )
    assert outputs[-1]["status"] == "draft"
    client, user_id, conversation_id, _ = research_chat
    with client.app.state.disciplinary_agent_scope() as application:
        assert application._tools_factory()._workflow.get_state(
            user_id=user_id, conversation_id=conversation_id,
        )["theory_plan_id"] is None


@pytest.mark.parametrize("changed_field", ["reason", "responsibility", "new_version", "new_id"])
def test_chat_confirmation_cannot_save_a_different_plan(research_chat, changed_field):
    payload = research_chat[3]
    _, proposals, _ = chat_turn(
        research_chat, prompt="提出方案", calls=[("propose_theory_plan", payload)], key="plan-a",
    )
    changed = deepcopy(payload)
    if changed_field == "reason":
        changed["decisions"][0]["reason"] = "改动后的理由"
    else:
        changed["use_assignments"][0]["responsibility"] = "另一版解释责任"
    if changed_field in {"new_version", "new_id"}:
        if changed_field == "new_id":
            changed = payload
        chat_turn(
            research_chat, prompt="换一版", calls=[("propose_theory_plan", changed)], key="plan-b",
        )
        changed = payload
    _, outputs, _ = chat_turn(
        research_chat, prompt="确认",
        calls=[("save_confirmed_theory_plan", save_payload(proposals[0], changed))],
        key="save-different-plan",
    )
    assert outputs[-1]["status"] == "draft"
    client, user_id, conversation_id, _ = research_chat
    with client.app.state.disciplinary_agent_scope() as application:
        assert application._tools_factory()._workflow.get_state(
            user_id=user_id, conversation_id=conversation_id,
        )["theory_plan_id"] is None


def test_replaying_an_older_user_message_cannot_confirm_a_newly_displayed_plan(research_chat):
    with pytest.raises(RuntimeError, match="synthetic interrupted response"):
        chat_turn(
            research_chat, prompt="确认", calls=[], key="older-confirmation", interrupted=True,
        )
    _, proposals, _ = chat_turn(
        research_chat, prompt="先给我看方案",
        calls=[("propose_theory_plan", research_chat[3])], key="newly-displayed-plan",
    )
    _, outputs, _ = chat_turn(
        research_chat, prompt="确认",
        calls=[("save_confirmed_theory_plan", save_payload(proposals[0], research_chat[3]))],
        key="older-confirmation",
    )
    assert outputs[-1]["status"] == "draft"
    client, user_id, conversation_id, _ = research_chat
    with client.app.state.disciplinary_agent_scope() as application:
        assert application._tools_factory()._workflow.get_state(
            user_id=user_id, conversation_id=conversation_id,
        )["theory_plan_id"] is None
