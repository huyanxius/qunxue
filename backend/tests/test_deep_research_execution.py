from types import SimpleNamespace

import pytest
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from qunxue_api.adapters.research_agent.pydantic_runner import PydanticAIKnowledgeRunner


def runner():
    return PydanticAIKnowledgeRunner(base_url="https://model.example.test/v1",
                                    api_key="test", model="test", timeout_seconds=10)


def tools(deep=True):
    return SimpleNamespace(release=SimpleNamespace(knowledge_release_id="test"),
                           evidence={}, selected_evidence_ids=(),
                           deep_research_enabled=deep, web_search_enabled=False)


def test_planner_returns_an_explicit_conversation_decision():
    r = runner()

    def model(messages, info):
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {
            "request_type": "conversation", "title": "问候",
        })])

    with r._planner_agent.override(model=FunctionModel(model)):
        result = r.prepare_research(prompt="你好", conversation=(), tools=tools(False),
                                    on_event=lambda e: pytest.fail("greeting made a card"))
    assert result == "conversation"


def test_planning_failure_is_not_replaced_by_an_invented_plan():
    r = runner()

    def unavailable(messages, info):
        raise RuntimeError("provider offline")

    with r._planner_agent.override(model=FunctionModel(unavailable)), pytest.raises(RuntimeError):
        r.prepare_research(prompt="研究高校食堂", conversation=(), tools=tools(False),
                           on_event=lambda e: pytest.fail("invented a plan"))


@pytest.mark.parametrize("stream", [False, True])
def test_research_reviews_evidence_before_showing_its_conclusion(stream):
    r = runner()
    visible = []

    def model(messages, info):
        # Investigation is internal. Its evidence review must reach the next
        # model turn, while only the final conclusion reaches the user stream.
        has_investigation = any(
            isinstance(p, TextPart) and p.content == "证据缺口：缺少本校时间序列"
            for m in messages for p in m.parts
        )
        return ModelResponse(parts=[TextPart(
            "结论：目前不能证实就餐频率下降" if has_investigation
            else "证据缺口：缺少本校时间序列"
        )])

    async def stream_model(messages, info):
        yield model(messages, info).parts[0].content

    with r._agent.override(model=FunctionModel(model, stream_function=stream_model)):
        if stream:
            result = r.run_stream(prompt="已确认提案：核实高校就餐趋势", conversation=(),
                                  tools=tools(), on_delta=visible.append)
        else:
            result = r.run(prompt="已确认提案：核实高校就餐趋势", conversation=(), tools=tools())
    assert result.answer == "结论：目前不能证实就餐频率下降"
    if stream:
        assert "".join(visible) == result.answer


def test_standard_answer_does_not_run_a_research_review():
    r = runner()
    with r._agent.override(model=FunctionModel(
        lambda messages, info: ModelResponse(parts=[TextPart("你好")])
    )):
        assert r.run(prompt="你好", conversation=(), tools=tools(False)).answer == "你好"
