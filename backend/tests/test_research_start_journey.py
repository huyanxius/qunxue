from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from qunxue_api.adapters.research_agent.document_tools import ResearchDocumentToolRegistry
from qunxue_api.adapters.sqlite import (
    AgentConversationRow,
    AgentRunRow,
    ResearchStartProposalRow,
)
from qunxue_api.adapters.sqlite.knowledge_catalog_model import KnowledgeReleaseRow
from qunxue_api.application import DisciplinaryAgentApplication, ResearchStartApplication
from qunxue_api.bootstrap import create_app
from qunxue_api.modules.agent_conversation import AgentRunResult, ConversationService
from qunxue_api.modules.knowledge_catalog import KnowledgeReleaseLevel, KnowledgeUsePurpose
from qunxue_api.modules.research_intake import (
    ResearchStartProposal,
    ResearchStartProposalStatus,
)


def _register(client: TestClient, *, email: str | None = None) -> UUID:
    response = client.post(
        "/api/session/register",
        headers={"Idempotency-Key": str(uuid4())},
        json={
            "email": email or f"{uuid4()}@example.com",
            "password": "research-passphrase",
        },
    )
    assert response.status_code == 201
    return UUID(response.json()["user"]["user_id"])


def _persist_completed_turn_proposal(
    client: TestClient,
    *,
    user_id: UUID,
    phenomenon: str = "社区成员流动正在改变邻里互助",
) -> dict[str, object]:
    with client.app.state.disciplinary_agent_scope() as application:
        execution = application.run_turn(
            user_id=user_id,
            conversation_id=None,
            prompt="请帮我把这个现象整理成研究起点",
            idempotency_key=str(uuid4()),
            workspace="research",
        )
        assert execution.turn is not None
        tools = application._tools_factory()
        tools.enable_research_document_tools()
        tools.bind_agent_context(
            user_id=user_id,
            conversation_id=execution.conversation.conversation_id,
            agent_run_id=execution.run_id,
            agent_turn_id=execution.turn.turn_id,
        )
        preview = tools.propose_start_research(
            phenomenon=phenomenon,
            research_intent="解释互助关系变化的机制",
            context="城市社区",
        )
        tools.finalize_agent_turn(source_turn_id=execution.turn.turn_id)
    return preview


def _confirmation_payload(proposal: dict[str, object]) -> dict[str, object]:
    return {
        "expected_version": proposal["version"],
        "phenomenon": proposal["phenomenon"],
        "research_intent": proposal["research_intent"],
        "context": proposal["context"],
    }


def test_run_turn_finalizes_model_proposal_against_its_persisted_turn() -> None:
    persisted: list[ResearchStartProposal] = []

    class Catalog:
        def current_release(self, *, purpose):
            del purpose
            return SimpleNamespace(knowledge_release_id="release-fixed")

    class Workflow:
        def restore(self, **_payload):
            return {"task_id": None, "theory_plan_id": None}

        def prepare_start_proposal(self, **payload):
            return ResearchStartProposal(
                proposal_id=UUID(int=10),
                user_id=payload["user_id"],
                conversation_id=payload["conversation_id"],
                source_run_id=payload["source_run_id"],
                source_turn_id=payload["source_turn_id"],
                knowledge_release_id=payload["knowledge_release_id"],
                phenomenon=payload["phenomenon"],
                research_intent=payload["research_intent"],
                context=payload["context"],
                version=1,
                status=ResearchStartProposalStatus.PENDING_CONFIRMATION,
                created_at=datetime(2026, 8, 22, tzinfo=UTC),
            )

        def persist_completed_turn_proposal(self, proposal):
            persisted.append(proposal)
            return proposal

    workflow = Workflow()
    registry = ResearchDocumentToolRegistry(
        catalog=Catalog(),
        documents=object(),
        proposals=object(),
        workflow=workflow,
    )

    class Runner:
        def run(self, *, prompt, conversation, tools):
            del prompt, conversation
            proposed = tools.propose_start_research(
                phenomenon="社区成员流动正在改变邻里互助",
                research_intent="解释互助变化",
                context="城市社区",
            )
            assert proposed["status"] == "pending_confirmation"
            return AgentRunResult(
                answer="我整理了一份研究起点，请确认后再创建研究。",
                citations=(),
                release_id="release-fixed",
                provider="test",
                model="test",
            )

    application = DisciplinaryAgentApplication(
        conversations=ConversationService.in_memory(),
        runner=Runner(),
        tools_factory=lambda: registry,
    )
    execution = application.run_turn(
        user_id=UUID(int=1),
        conversation_id=None,
        prompt="我想研究社区互助",
        idempotency_key="research-start-turn",
        workspace="research",
    )

    assert execution.turn is not None
    assert len(persisted) == 1
    assert persisted[0].source_run_id == execution.run_id
    assert persisted[0].source_turn_id == execution.turn.turn_id
    assert not hasattr(registry, "create_confirmed_research_task")


def test_completed_agent_turn_persists_a_refreshable_start_proposal(client: TestClient) -> None:
    user_id = _register(client)

    proposed = _persist_completed_turn_proposal(client, user_id=user_id)
    restored = client.get(
        f"/api/agent/conversations/{proposed['conversation_id']}/research-start-proposal"
    )

    assert proposed["status"] == "pending_confirmation"
    assert proposed["requires_user_confirmation"] is True
    assert restored.status_code == 200
    assert restored.json() == {**proposed, "created_at": restored.json()["created_at"]}
    restored_created_at = datetime.fromisoformat(
        restored.json()["created_at"].replace("Z", "+00:00")
    )
    assert restored_created_at == datetime.fromisoformat(str(proposed["created_at"]))
    assert restored.json()["source_run_id"]
    assert restored.json()["source_turn_id"]
    assert restored.json()["knowledge_release_id"]


def test_confirm_start_is_idempotent_and_persists_task_provenance(client: TestClient) -> None:
    user_id = _register(client)
    proposal = _persist_completed_turn_proposal(client, user_id=user_id)
    headers = {"Idempotency-Key": str(uuid4())}
    payload = _confirmation_payload(proposal)

    first = client.post(
        f"/api/agent/research-start-proposals/{proposal['proposal_id']}/confirm",
        headers=headers,
        json=payload,
    )
    replay = client.post(
        f"/api/agent/research-start-proposals/{proposal['proposal_id']}/confirm",
        headers=headers,
        json=payload,
    )

    assert first.status_code == 201
    assert replay.status_code == 201
    assert replay.json() == first.json()
    navigation = first.json()["navigation"]
    assert first.json()["status"] == "task_bound"
    assert first.json()["task_id"] == navigation["task_id"]
    assert first.json()["conversation_id"] == proposal["conversation_id"]
    assert navigation["current_stage"] == "theory_matching"
    assert navigation["stage_label"] == "理论匹配"
    assert navigation["next_action_label"] == "开始理论匹配"
    assert navigation["resume_path"] == f"/research/{navigation['task_id']}/match"
    assert navigation["knowledge_release_id"] == proposal["knowledge_release_id"]
    assert navigation["conversation_id"] == proposal["conversation_id"]
    assert navigation["source_turn_id"] == proposal["source_turn_id"]
    assert navigation["source_run_id"] == proposal["source_run_id"]
    assert navigation["phenomenon_summary"]["phenomenon"] == payload["phenomenon"]
    listed = client.get("/api/research-tasks")
    assert listed.status_code == 200
    assert listed.json()["items"] == [navigation]


def test_same_confirmation_key_with_changed_payload_returns_conflict(client: TestClient) -> None:
    user_id = _register(client)
    proposal = _persist_completed_turn_proposal(client, user_id=user_id)
    headers = {"Idempotency-Key": str(uuid4())}
    payload = _confirmation_payload(proposal)
    first = client.post(
        f"/api/agent/research-start-proposals/{proposal['proposal_id']}/confirm",
        headers=headers,
        json=payload,
    )
    changed = client.post(
        f"/api/agent/research-start-proposals/{proposal['proposal_id']}/confirm",
        headers=headers,
        json={**payload, "phenomenon": "同一幂等键不能确认另一份现象"},
    )

    assert first.status_code == 201
    assert changed.status_code == 409
    assert changed.json()["error"]["code"] == "research_start_idempotency_conflict"


def test_first_confirmation_cannot_change_the_persisted_agent_proposal(
    client: TestClient,
) -> None:
    user_id = _register(client)
    proposal = _persist_completed_turn_proposal(client, user_id=user_id)
    changed_payload = {
        **_confirmation_payload(proposal),
        "phenomenon": "确认请求不能替换 Agent 已持久化的研究现象",
    }

    changed = client.post(
        f"/api/agent/research-start-proposals/{proposal['proposal_id']}/confirm",
        headers={"Idempotency-Key": "changed-first-confirmation"},
        json=changed_payload,
    )

    assert changed.status_code == 409
    assert changed.json()["error"]["code"] == "research_start_proposal_conflict"
    assert client.get("/api/research-tasks").json()["items"] == []
    restored = client.get(
        f"/api/agent/conversations/{proposal['conversation_id']}/research-start-proposal"
    )
    assert restored.status_code == 200
    assert restored.json()["status"] == "pending_confirmation"
    assert restored.json()["phenomenon"] == proposal["phenomenon"]


def test_failed_confirmation_rolls_back_and_can_retry_without_a_duplicate(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = _register(client)
    proposal = _persist_completed_turn_proposal(client, user_id=user_id)
    endpoint = f"/api/agent/research-start-proposals/{proposal['proposal_id']}/confirm"
    payload = _confirmation_payload(proposal)

    def fail_after_task_creation(*_args, **_kwargs):
        raise RuntimeError("simulated phenomenon write failure")

    with monkeypatch.context() as scoped:
        scoped.setattr(
            ResearchStartApplication,
            "_confirm_phenomenon",
            fail_after_task_creation,
        )
        with pytest.raises(RuntimeError, match="simulated phenomenon write failure"):
            client.post(
                endpoint,
                headers={"Idempotency-Key": "retry-after-rollback"},
                json=payload,
            )

    assert client.get("/api/research-tasks").json()["items"] == []
    journey = client.get(f"/api/agent/conversations/{proposal['conversation_id']}/journey")
    assert journey.status_code == 200
    assert journey.json()["status"] == "proposal_pending"

    retried = client.post(
        endpoint,
        headers={"Idempotency-Key": "retry-after-rollback"},
        json=payload,
    )
    assert retried.status_code == 201
    task_id = retried.json()["task_id"]
    listed = client.get("/api/research-tasks").json()["items"]
    assert [item["task_id"] for item in listed] == [task_id]


def test_m4_uses_the_task_release_even_after_a_new_release_becomes_current(
    client: TestClient,
) -> None:
    user_id = _register(client)
    proposal = _persist_completed_turn_proposal(client, user_id=user_id)
    confirmed = client.post(
        f"/api/agent/research-start-proposals/{proposal['proposal_id']}/confirm",
        headers={"Idempotency-Key": "confirm-pinned-release"},
        json=_confirmation_payload(proposal),
    )
    assert confirmed.status_code == 201
    navigation = confirmed.json()["navigation"]
    pinned_release_id = proposal["knowledge_release_id"]

    with client.app.state.database.session() as session:
        session.add(
            KnowledgeReleaseRow(
                knowledge_release_id="knowledge-final-after-task-start",
                level=KnowledgeReleaseLevel.FINAL.value,
                content_hash="sha256:knowledge-final-after-task-start",
                build_config_version="test-final-v1",
                manifest={
                    "knowledge_ids": [],
                    "relation_ids": [],
                    "theory_ids": [],
                    "source_ids": [],
                    "review_record_ids": [],
                    "artifact_hashes": [],
                },
                is_current=False,
                built_at=datetime.now(UTC),
            )
        )
    assert (
        client.app.state.knowledge_catalog.current_release(
            purpose=KnowledgeUsePurpose.MATCH
        ).knowledge_release_id
        == "knowledge-final-after-task-start"
    )

    phenomenon = navigation["phenomenon_summary"]
    started = client.post(
        f"/api/research-tasks/{navigation['task_id']}/match-runs",
        headers={"Idempotency-Key": "start-with-pinned-release"},
        json={
            "expected_task_version": navigation["version"],
            "phenomenon_query_id": phenomenon["phenomenon_query_id"],
            "phenomenon_version": phenomenon["version"],
            "knowledge_release_id": pinned_release_id,
        },
    )

    assert started.status_code == 200
    assert started.json()["knowledge_release_id"] == pinned_release_id


def test_agent_workflow_retries_a_no_reliable_candidate_match(
    client: TestClient,
) -> None:
    user_id = _register(client)
    proposal = _persist_completed_turn_proposal(client, user_id=user_id)
    confirmed = client.post(
        f"/api/agent/research-start-proposals/{proposal['proposal_id']}/confirm",
        headers={"Idempotency-Key": "confirm-before-agent-retry"},
        json=_confirmation_payload(proposal),
    )
    navigation = confirmed.json()["navigation"]
    phenomenon = navigation["phenomenon_summary"]
    first = client.post(
        f"/api/research-tasks/{navigation['task_id']}/match-runs",
        headers={"Idempotency-Key": "first-empty-match"},
        json={
            "expected_task_version": navigation["version"],
            "phenomenon_query_id": phenomenon["phenomenon_query_id"],
            "phenomenon_version": phenomenon["version"],
            "knowledge_release_id": navigation["knowledge_release_id"],
        },
    )
    assert first.status_code == 200
    assert first.json()["status"] == "no_reliable_candidate"

    with client.app.state.disciplinary_agent_scope() as application:
        tools = application._tools_factory()
        tools.enable_research_document_tools()
        tools.bind_agent_context(
            user_id=user_id,
            conversation_id=UUID(str(proposal["conversation_id"])),
            agent_run_id=UUID(str(proposal["source_run_id"])),
            agent_turn_id=UUID(str(proposal["source_turn_id"])),
        )
        retried = tools.start_theory_matching()

    assert retried["match_run_id"] != first.json()["match_run_id"]


def test_concurrent_confirmation_creates_only_one_research_task(client: TestClient) -> None:
    user_id = _register(client)
    proposal = _persist_completed_turn_proposal(client, user_id=user_id)
    payload = _confirmation_payload(proposal)
    workers = 4
    barrier = Barrier(workers)

    def confirm(index: int) -> tuple[int, str]:
        barrier.wait()
        response = client.post(
            f"/api/agent/research-start-proposals/{proposal['proposal_id']}/confirm",
            headers={"Idempotency-Key": f"confirm-concurrently-{index}"},
            json=payload,
        )
        return response.status_code, response.json()["navigation"]["task_id"]

    with ThreadPoolExecutor(max_workers=workers) as executor:
        results = list(executor.map(confirm, range(workers)))

    assert {status for status, _task_id in results} == {201}
    assert len({task_id for _status, task_id in results}) == 1
    listed = client.get("/api/research-tasks")
    assert listed.status_code == 200
    assert [item["task_id"] for item in listed.json()["items"]] == [results[0][1]]


def test_two_application_instances_confirm_the_same_proposal_once(client: TestClient) -> None:
    user_id = _register(client)
    proposal = _persist_completed_turn_proposal(client, user_id=user_id)
    payload = _confirmation_payload(proposal)
    second_app = create_app(
        settings=client.app.state.settings,
        database=client.app.state.database,
    )
    barrier = Barrier(2)

    with TestClient(second_app) as second_client:
        second_client.cookies.update(client.cookies)

        def confirm(request_client: TestClient, key: str) -> tuple[int, str]:
            barrier.wait()
            response = request_client.post(
                f"/api/agent/research-start-proposals/{proposal['proposal_id']}/confirm",
                headers={"Idempotency-Key": key},
                json=payload,
            )
            return response.status_code, response.json()["navigation"]["task_id"]

        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(confirm, client, "confirm-instance-one")
            second = executor.submit(confirm, second_client, "confirm-instance-two")
            results = [first.result(), second.result()]

    assert {status for status, _task_id in results} == {201}
    assert len({task_id for _status, task_id in results}) == 1
    listed = client.get("/api/research-tasks")
    assert [item["task_id"] for item in listed.json()["items"]] == [results[0][1]]


def test_proposal_and_journey_are_hidden_from_another_user(client: TestClient) -> None:
    owner_id = _register(client)
    proposal = _persist_completed_turn_proposal(client, user_id=owner_id)
    client.cookies.clear()
    _register(client)

    proposal_response = client.get(
        f"/api/agent/conversations/{proposal['conversation_id']}/research-start-proposal"
    )
    journey_response = client.get(f"/api/agent/conversations/{proposal['conversation_id']}/journey")
    confirm_response = client.post(
        f"/api/agent/research-start-proposals/{proposal['proposal_id']}/confirm",
        headers={"Idempotency-Key": str(uuid4())},
        json=_confirmation_payload(proposal),
    )

    assert proposal_response.status_code == 404
    assert journey_response.status_code == 404
    assert confirm_response.status_code == 404


def test_proposal_from_an_unfinished_agent_run_cannot_be_confirmed(client: TestClient) -> None:
    user_id = _register(client)
    conversation_id = uuid4()
    run_id = uuid4()
    turn_id = uuid4()
    proposal_id = uuid4()
    now = datetime.now(UTC)
    release_id = client.get("/api/knowledge/releases/current").json()["knowledge_release_id"]
    with client.app.state.database.session() as session:
        session.add(
            AgentConversationRow(
                conversation_id=str(conversation_id),
                user_id=str(user_id),
                title="尚未完成的回答",
                version=1,
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            AgentRunRow(
                run_id=str(run_id),
                turn_id=str(turn_id),
                conversation_id=str(conversation_id),
                user_id=str(user_id),
                idempotency_key="unfinished-research-start-run",
                status="running",
                provider="test",
                model="test",
                knowledge_release_id=release_id,
                usage={},
                tool_summary=[],
                started_at=now,
            )
        )
        session.add(
            ResearchStartProposalRow(
                proposal_id=str(proposal_id),
                user_id=str(user_id),
                conversation_id=str(conversation_id),
                source_run_id=str(run_id),
                source_turn_id=str(turn_id),
                knowledge_release_id=release_id,
                phenomenon="尚未完成回答里的研究现象",
                research_intent=None,
                context=None,
                version=1,
                status="pending_confirmation",
                created_at=now,
            )
        )

    response = client.post(
        f"/api/agent/research-start-proposals/{proposal_id}/confirm",
        headers={"Idempotency-Key": "confirm-unfinished-run"},
        json={
            "expected_version": 1,
            "phenomenon": "尚未完成回答里的研究现象",
            "research_intent": None,
            "context": None,
        },
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "research_start_source_incomplete"
    assert client.get("/api/research-tasks").json()["items"] == []
