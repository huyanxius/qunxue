from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from pydantic_ai.models.function import DeltaToolCall, FunctionModel

from qunxue_api.adapters.research_agent import ResearchDocumentToolRegistry
from qunxue_api.adapters.research_agent.pydantic_runner import (
    PydanticAIKnowledgeRunner,
)
from qunxue_api.modules.research_analysis import (
    AnalysisCode,
    AnalysisMemo,
    AnalysisMemoKind,
    CaseComparison,
    ComparisonFinding,
    ComparisonFindingKind,
    NextResearchStep,
)

USER_ID = UUID("00000000-0000-0000-0000-000000000201")
TASK_ID = UUID("00000000-0000-0000-0000-000000000202")
CONVERSATION_ID = UUID("00000000-0000-0000-0000-000000000203")
RUN_ID = UUID("00000000-0000-0000-0000-000000000204")
TURN_ID = UUID("00000000-0000-0000-0000-000000000205")
ANNOTATION_ID = UUID("00000000-0000-0000-0000-000000000206")


class _Catalog:
    def current_release(self, *, purpose):
        del purpose
        return SimpleNamespace(
            knowledge_release_id="release-analysis-agent",
            content_hash="sha256:analysis-agent",
        )


class _Materials:
    def list(self, **_kwargs):
        return ()


class _AnalysisFacade:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def get_for_agent(self, **payload):
        self.calls.append(("get", payload))
        return {
            "schema_version": "research-analysis-v1",
            "annotations": [],
            "codes": [],
            "memos": [],
            "comparisons": [],
        }

    def propose_code_from_agent(self, **payload):
        self.calls.append(("code", payload))
        return AnalysisCode.candidate(
            user_id=payload["user_id"],
            task_id=payload["task_id"],
            label=payload["label"],
            definition=payload["definition"],
            annotation_ids=payload["annotation_ids"],
            rationale=payload["rationale"],
            now=datetime.now(UTC),
        )

    def propose_memo_from_agent(self, **payload):
        self.calls.append(("memo", payload))
        return AnalysisMemo.create_candidate(
            user_id=payload["user_id"],
            task_id=payload["task_id"],
            title=payload["title"],
            content=payload["content"],
            memo_kind=AnalysisMemoKind(payload["memo_kind"]),
            annotation_ids=payload["annotation_ids"],
            code_ids=payload["code_ids"],
            now=datetime.now(UTC),
        )

    def propose_coding_plan_from_agent(self, **payload):
        self.calls.append(("coding_plan", payload))
        return {"plan_id": "plan-agent", "status": "candidate", "items": payload["items"]}

    def retrieve_coded_segments(self, **payload):
        self.calls.append(("retrieved", payload))
        return [{"quote": "原文片段", "code_id": "code-confirmed"}]

    def get_comparison_context_for_agent(self, **payload):
        self.calls.append(("comparison_context", payload))
        return {
            "schema_version": "research-comparison-context-v1",
            "case_labels": payload["case_labels"],
            "time_labels": payload["time_labels"],
            "annotations": [],
            "confirmed_codes": [],
            "confirmed_memos": [],
            "confirmed_comparisons": [],
        }

    def propose_comparison_from_agent(self, **payload):
        self.calls.append(("comparison", payload))
        return CaseComparison.create(
            user_id=payload["user_id"],
            task_id=payload["task_id"],
            title=payload["title"],
            question=payload["question"],
            case_labels=payload["case_labels"],
            time_labels=payload["time_labels"],
            findings=payload["findings"],
            competing_explanations=payload["competing_explanations"],
            evidence_gaps=payload["evidence_gaps"],
            next_steps=payload["next_steps"],
            theory_implication=payload["theory_implication"],
            conversation_id=payload["conversation_id"],
            agent_run_id=payload["agent_run_id"],
            agent_turn_id=payload["agent_turn_id"],
            tool_call_id=payload["tool_call_id"],
            now=datetime.now(UTC),
        )


def _registry(
    analysis: _AnalysisFacade,
    *,
    task_id: UUID | None = TASK_ID,
    materials: object | None = None,
) -> ResearchDocumentToolRegistry:
    registry = ResearchDocumentToolRegistry(
        catalog=_Catalog(),
        documents=SimpleNamespace(),
        proposals=SimpleNamespace(),
        materials=_Materials() if materials is None else materials,
        analysis=analysis,
    )
    registry.bind_agent_context(
        user_id=USER_ID,
        conversation_id=CONVERSATION_ID,
        agent_run_id=RUN_ID,
        agent_turn_id=TURN_ID,
        task_id=task_id,
    )
    return registry


def test_analysis_registry_persists_candidate_provenance_without_deciding():
    facade = _AnalysisFacade()
    registry = _registry(facade)

    snapshot = registry.get_research_analysis()
    code = registry.propose_analysis_code(
        label="照护责任性别化",
        definition="照护责任集中到女性家庭成员。",
        annotation_ids=[str(ANNOTATION_ID)],
        rationale="该片段支持候选编码，但需要研究者跨材料复核。",
        tool_call_id="call-analysis-code",
    )
    memo = registry.propose_analysis_memo(
        title="替代解释待检验",
        content="经济资源差异也可能解释责任分配。",
        memo_kind="analytic",
        annotation_ids=[str(ANNOTATION_ID)],
        code_ids=[code["code_id"]],
        tool_call_id="call-analysis-memo",
    )
    comparison_context = registry.get_research_comparison_context(
        case_labels=["家庭 A", "家庭 B"],
        time_labels=["迁移前", "迁移后"],
    )
    comparison = registry.propose_case_comparison(
        title="两个家庭的照护安排",
        question="迁移是否必然强化性别化照护？",
        case_labels=["家庭 A", "家庭 B"],
        time_labels=["迁移前", "迁移后"],
        findings=[
            {
                "kind": "support",
                "statement": "家庭 A 的照护仍集中于女性。",
                "annotation_ids": [str(ANNOTATION_ID)],
            },
            {
                "kind": "counterexample",
                "statement": "家庭 B 的兄弟共同承担照护。",
                "annotation_ids": [str(ANNOTATION_ID)],
            },
        ],
        competing_explanations=["邻里互助网络"],
        evidence_gaps=["缺少家庭 B 迁移前记录"],
        next_steps=[
            {
                "kind": "interview",
                "action": "补访家庭 B 的迁移前照护安排",
                "priority": "high",
            }
        ],
        theory_implication="需要竞争检验性别分工与邻里网络解释。",
        tool_call_id="call-analysis-comparison",
    )

    assert snapshot["schema_version"] == "research-analysis-v1"
    assert code["status"] == "candidate"
    assert memo["status"] == "candidate"
    assert comparison_context["schema_version"] == "research-comparison-context-v1"
    assert comparison["status"] == "candidate"
    assert code["requires_user_confirmation"] is True
    assert memo["requires_user_confirmation"] is True
    assert comparison["requires_user_confirmation"] is True
    expected_provenance = {
        "user_id": USER_ID,
        "task_id": TASK_ID,
        "conversation_id": CONVERSATION_ID,
        "agent_run_id": RUN_ID,
        "agent_turn_id": TURN_ID,
    }
    assert facade.calls[0] == ("get", {"user_id": USER_ID, "task_id": TASK_ID})
    for call_name, tool_call_id in (
        ("code", "call-analysis-code"),
        ("memo", "call-analysis-memo"),
        ("comparison", "call-analysis-comparison"),
    ):
        payload = next(payload for name, payload in facade.calls if name == call_name)
        assert {key: payload[key] for key in expected_provenance} == expected_provenance
        assert payload["tool_call_id"] == tool_call_id
    context_payload = next(
        payload for name, payload in facade.calls if name == "comparison_context"
    )
    assert context_payload == {
        "user_id": USER_ID,
        "task_id": TASK_ID,
        "case_labels": ("家庭 A", "家庭 B"),
        "time_labels": ("迁移前", "迁移后"),
    }
    comparison_payload = next(
        payload for name, payload in facade.calls if name == "comparison"
    )
    assert comparison_payload["findings"] == (
        ComparisonFinding(
            kind=ComparisonFindingKind.SUPPORT,
            statement="家庭 A 的照护仍集中于女性。",
            annotation_ids=(ANNOTATION_ID,),
        ),
        ComparisonFinding(
            kind=ComparisonFindingKind.COUNTEREXAMPLE,
            statement="家庭 B 的兄弟共同承担照护。",
            annotation_ids=(ANNOTATION_ID,),
        ),
    )
    assert comparison_payload["next_steps"] == (
        NextResearchStep(
            kind="interview",
            action="补访家庭 B 的迁移前照护安排",
            priority="high",
        ),
    )


def test_analysis_registry_exposes_coding_plan_and_confirmed_retrieval():
    facade = _AnalysisFacade()
    registry = _registry(facade)

    plan = registry.propose_coding_plan(
        title="归入既有代码", rationale="与代码本定义一致。", items=[{
            "material_id": str(UUID(int=301)), "parse_id": str(UUID(int=302)),
            "segment_id": "segment-2", "quote_start": 0, "quote_end": 3,
            "code_id": str(UUID(int=303)), "confidence": 0.9, "rationale": "原文支持。",
        }], tool_call_id="call-plan",
    )
    retrieved = registry.retrieve_coded_segments(
        code_ids=[str(UUID(int=303))], query="原文", limit=5,
    )

    assert plan["status"] == "candidate"
    assert plan["requires_user_confirmation"] is True
    assert retrieved == [{"quote": "原文片段", "code_id": "code-confirmed"}]
    plan_payload = next(payload for name, payload in facade.calls if name == "coding_plan")
    assert plan_payload["tool_call_id"] == "call-plan"


def test_pydantic_runner_exposes_only_analysis_read_and_candidate_tools():
    facade = _AnalysisFacade()
    registry = _registry(facade)
    visible_tools: set[str] = set()

    async def model_stream(messages, info):
        del messages
        visible_tools.update(tool.name for tool in info.function_tools)
        call_names = [name for name, _payload in facade.calls]
        if "get" not in call_names:
            yield {
                0: DeltaToolCall(
                    name="get_research_analysis",
                    json_args="{}",
                    tool_call_id="call-analysis-read",
                )
            }
        elif "code" not in call_names:
            yield {
                0: DeltaToolCall(
                    name="propose_analysis_code",
                    json_args=(
                        '{"label":"照护责任性别化",'
                        '"definition":"照护责任集中到女性家庭成员。",'
                        f'"annotation_ids":["{ANNOTATION_ID}"],'
                        '"rationale":"需要研究者复核。"}'
                    ),
                    tool_call_id="call-analysis-code-runner",
                )
            }
        elif "memo" not in call_names:
            code_id = next(
                payload.get("created_code_id", "00000000-0000-0000-0000-000000000207")
                for name, payload in facade.calls
                if name == "code"
            )
            yield {
                0: DeltaToolCall(
                    name="propose_analysis_memo",
                    json_args=(
                        '{"title":"替代解释待检验",'
                        '"content":"经济资源差异也可能解释责任分配。",'
                        '"memo_kind":"analytic",'
                        f'"annotation_ids":["{ANNOTATION_ID}"],'
                        f'"code_ids":["{code_id}"]}}'
                    ),
                    tool_call_id="call-analysis-memo-runner",
                )
            }
        elif "comparison_context" not in call_names:
            yield {
                0: DeltaToolCall(
                    name="get_research_comparison_context",
                    json_args=(
                        '{"case_labels":["家庭 A","家庭 B"],'
                        '"time_labels":["迁移前","迁移后"]}'
                    ),
                    tool_call_id="call-analysis-comparison-context-runner",
                )
            }
        elif "comparison" not in call_names:
            yield {
                0: DeltaToolCall(
                    name="propose_case_comparison",
                    json_args=(
                        '{"title":"两个家庭的照护安排",'
                        '"question":"迁移是否必然强化性别化照护？",'
                        '"case_labels":["家庭 A","家庭 B"],'
                        '"time_labels":["迁移前","迁移后"],'
                        '"findings":[{"kind":"support",'
                        '"statement":"家庭 A 的照护仍集中于女性。",'
                        f'"annotation_ids":["{ANNOTATION_ID}"]}},'
                        '{"kind":"counterexample",'
                        '"statement":"家庭 B 的兄弟共同承担照护。",'
                        f'"annotation_ids":["{ANNOTATION_ID}"]}}],'
                        '"competing_explanations":["邻里互助网络"],'
                        '"evidence_gaps":["缺少家庭 B 迁移前记录"],'
                        '"next_steps":[{"kind":"interview",'
                        '"action":"补访家庭 B 的迁移前照护安排",'
                        '"priority":"high"}],'
                        '"theory_implication":"需要竞争检验性别分工与邻里网络解释。"}'
                    ),
                    tool_call_id="call-analysis-comparison-runner",
                )
            }
        else:
            yield "已形成待你确认的编码、备忘与案例比较候选。"

    runner = PydanticAIKnowledgeRunner(
        base_url="https://api.deepseek.com",
        api_key="local-test-key",
        model="deepseek-v4-flash",
        timeout_seconds=30,
    )
    events = []
    with runner._agent.override(model=FunctionModel(stream_function=model_stream)):
        result = runner.run_stream(
            prompt="基于现有标注提出候选编码和分析备忘",
            conversation=(),
            tools=registry,
            on_delta=lambda _delta: None,
            on_tool_event=events.append,
        )

    assert result.answer == "已形成待你确认的编码、备忘与案例比较候选。"
    assert {
        "get_research_analysis",
        "propose_analysis_code",
        "propose_analysis_memo",
        "get_research_comparison_context",
        "propose_case_comparison",
    } <= visible_tools
    assert not any(
        marker in tool_name
        for tool_name in visible_tools
        for marker in ("decide_analysis", "confirm_analysis", "reject_analysis")
    )
    code_payload = next(payload for name, payload in facade.calls if name == "code")
    memo_payload = next(payload for name, payload in facade.calls if name == "memo")
    comparison_payload = next(
        payload for name, payload in facade.calls if name == "comparison"
    )
    assert code_payload["tool_call_id"] == "call-analysis-code-runner"
    assert memo_payload["tool_call_id"] == "call-analysis-memo-runner"
    assert comparison_payload["tool_call_id"] == "call-analysis-comparison-runner"
    assert {
        event.tool
        for event in events
        if event.phase == "finished"
    } >= {
        "get_research_analysis",
        "propose_analysis_code",
        "propose_analysis_memo",
        "get_research_comparison_context",
        "propose_case_comparison",
    }


def test_analysis_tools_require_task_material_and_complete_run_provenance():
    facade = _AnalysisFacade()
    registry_without_task = _registry(facade, task_id=None)
    registry_without_materials = ResearchDocumentToolRegistry(
        catalog=_Catalog(),
        documents=SimpleNamespace(),
        proposals=SimpleNamespace(),
        materials=None,
        analysis=facade,
    )
    registry_without_materials.bind_agent_context(
        user_id=USER_ID,
        conversation_id=CONVERSATION_ID,
        agent_run_id=RUN_ID,
        agent_turn_id=TURN_ID,
        task_id=TASK_ID,
    )

    assert registry_without_task.research_analysis_tools_enabled is False
    assert registry_without_materials.research_analysis_tools_enabled is False


def test_bootstrap_injects_task_scoped_analysis_facade(client: TestClient):
    session = client.post(
        "/api/session/register",
        headers={"Idempotency-Key": str(uuid4())},
        json={
            "email": f"analysis-agent-{uuid4()}@example.com",
            "password": "research-passphrase",
        },
    )
    assert session.status_code == 201
    user_id = UUID(session.json()["user"]["user_id"])
    task = client.post(
        "/api/research-tasks",
        headers={"Idempotency-Key": str(uuid4())},
        json={"entry_type": "direct_input"},
    )
    assert task.status_code == 201
    task_id = UUID(task.json()["task_id"])

    with client.app.state.disciplinary_agent_scope() as application:
        registry = application._tools_factory()
        registry.bind_agent_context(
            user_id=user_id,
            conversation_id=uuid4(),
            agent_run_id=uuid4(),
            agent_turn_id=uuid4(),
            task_id=task_id,
        )

        assert registry.research_analysis_tools_enabled is True
        assert registry.get_research_analysis()["schema_version"] == (
            "research-analysis-v1"
        )
