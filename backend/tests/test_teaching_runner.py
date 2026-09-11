from types import SimpleNamespace

from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel

from qunxue_api.adapters.research_agent.pydantic_runner import PydanticAIKnowledgeRunner


def test_teaching_uses_authorized_snapshot_without_research_tools():
    runner = PydanticAIKnowledgeRunner(
        base_url="https://example.invalid/v1",
        api_key="test",
        model="test",
        timeout_seconds=30,
        direct_task=True,
    )

    def respond(messages, info):
        assert not info.function_tools
        assert "已授权课堂输入" in str(messages)
        return ModelResponse(parts=[TextPart('{"stage":"diagnostic","diagnostic_questions":[]}')])

    tools = SimpleNamespace(evidence={}, release=SimpleNamespace(knowledge_release_id="test"))
    runner.prepare_research(
        prompt="已授权课堂输入", conversation=(), tools=tools,
        on_event=lambda event: (_ for _ in ()).throw(AssertionError("unexpected planning")),
    )
    with runner._task_agent.override(model=FunctionModel(respond)):
        result = runner.run(prompt="已授权课堂输入", conversation=(), tools=tools)
    assert result.answer == '{"stage":"diagnostic","diagnostic_questions":[]}'
    assert result.provider == "pydantic-ai"
