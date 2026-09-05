from pydantic_ai.models.function import DeltaToolCall, FunctionModel
from test_research_map_tool import _Catalog

from qunxue_api.adapters.research_agent.catalog_tools import KnowledgeToolRegistry
from qunxue_api.adapters.research_agent.pydantic_runner import PydanticAIKnowledgeRunner


def test_research_ask_is_a_persistable_tool_without_writing_research_state():
    events = []
    calls = 0

    async def model_stream(messages, info):
        nonlocal calls
        calls += 1
        if calls == 1:
            yield {
                0: DeltaToolCall(
                    name="ask_research_question",
                    json_args='{"question":"你能接触到哪些人？","options":["社团成员","其他同学"]}',
                    tool_call_id="ask-1",
                )
            }
        else:
            yield "先确认可接触的研究对象。"

    tools = KnowledgeToolRegistry(_Catalog())
    tools.enable_research_map()
    runner = PydanticAIKnowledgeRunner(
        base_url="https://api.deepseek.com",
        api_key="local-test-key",
        model="deepseek-v4-flash",
        timeout_seconds=30,
    )
    with runner._agent.override(model=FunctionModel(stream_function=model_stream)):
        result = runner.run_stream(
            prompt="一起拟定研究方案",
            conversation=(),
            tools=tools,
            on_delta=lambda _: None,
            on_tool_event=events.append,
        )
    finished = [
        event
        for event in events
        if event.tool == "ask_research_question" and event.phase == "finished"
    ]
    assert finished[0].output == {
        "question": "你能接触到哪些人？",
        "options": ["社团成员", "其他同学"],
    }
    assert tools.research_map["nodes"] == []
    assert result.answer
