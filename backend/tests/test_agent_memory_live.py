"""Opt-in real-model acceptance against a temporary fixture database, never production data."""

import json
import os
from contextlib import contextmanager
from uuid import uuid4

import pytest
from test_agent_memory import project, register, seed_learning_source

from qunxue_api.adapters.model import ModelRouteExecutor
from qunxue_api.adapters.research_agent.memory_extractor import PydanticMemoryExtractor
from qunxue_api.adapters.research_agent.pydantic_runner import PydanticAIKnowledgeRunner
from qunxue_api.bootstrap import _model_endpoints_from_settings
from qunxue_api.settings import Settings

pytestmark = pytest.mark.skipif(
    not os.environ.get("QUNXUE_MEMORY_LIVE_ENV_FILE"), reason="requires explicit live model config"
)


@pytest.fixture
def live_model():
    settings = Settings(_env_file=os.environ["QUNXUE_MEMORY_LIVE_ENV_FILE"])
    endpoint = _model_endpoints_from_settings(settings)[0]
    return endpoint, dict(
        base_url=endpoint.base_url,
        api_key=endpoint.api_key,
        model=endpoint.model,
        timeout_seconds=45,
        extra_headers=dict(endpoint.extra_headers),
    )


def test_live_model_remembers_recalls_corrects_and_forgets(client, live_model):
    endpoint, model_config = live_model
    original_scope = client.app.state.disciplinary_agent_scope
    router = ModelRouteExecutor(endpoints=(endpoint,))
    client.app.state.settings = client.app.state.settings.model_copy(
        update={"runtime_mode": "base"}
    )

    @contextmanager
    def live_scope():
        with original_scope() as application:
            application._runner = PydanticAIKnowledgeRunner(**model_config, route_executor=router)
            yield application

    client.app.state.disciplinary_agent_scope = live_scope
    register(client)
    task_id = project(client)

    def turn(prompt, task=None):
        response = client.post(
            "/api/agent/turns",
            headers={"Idempotency-Key": str(uuid4())},
            json={"message": prompt, "workspace": "research", "task_id": task},
        )
        assert response.status_code == 200
        assert "event: turn_failed" not in response.text
        events = []
        for block in response.text.split("\n\n"):
            if "data: " in block:
                events.append(json.loads(block.split("data: ", 1)[1]))
        print(json.dumps({"prompt": prompt, "events": events}, ensure_ascii=False))
        completed = next(
            event["conversation"] for event in reversed(events) if "conversation" in event
        )
        return completed["turns"][-1]["assistant"]["content"]

    turn("请记住我的长期偏好：回答先给结论。也请记住本项目的方法是半结构访谈。", task_id)
    user_entries = client.get("/api/memories").json()["items"]
    project_entries = client.get("/api/memories", params={"task_id": task_id}).json()["items"]
    assert any("结论" in entry["content"] for entry in user_entries)
    assert any("访谈" in entry["content"] for entry in project_entries)
    recalled = turn("我通常希望你怎样组织回答？这个项目用什么研究方法？只复述已有记忆。", task_id)
    assert "结论" in recalled and "访谈" in recalled
    turn("修改你对我的长期记忆：以后回答先给例子，再解释。请替换之前先给结论的偏好。", task_id)
    user_entries = client.get("/api/memories").json()["items"]
    assert any("例子" in entry["content"] for entry in user_entries)
    assert not any("先给结论" in entry["content"] for entry in user_entries)
    turn("请忘记本项目关于研究方法的记忆。", task_id)
    assert client.get("/api/memories", params={"task_id": task_id}).json()["items"] == []
    recalled = turn("只复述你知道的我的回答组织偏好。")
    assert "例子" in recalled


def test_live_model_learns_from_user_sources(plain_client, live_model):
    client = plain_client
    _, model_config = live_model
    learning_user = register(client)
    _, message = seed_learning_source(
        client,
        learning_user,
        content="我写社会学论文时一直使用 APA 第七版引用格式，这也是我今后的固定要求。",
    )
    extractor = PydanticMemoryExtractor(**model_config)

    def extract(batch):
        try:
            result = extractor(batch)
            print("Extraction:", result)
            return result
        except Exception as error:
            print("Extraction error:", type(error).__name__, getattr(error, "status_code", None))
            raise

    assert client.app.state.memory_worker.run_once(extractor=extract)
    learned = client.get("/api/memories").json()["items"]
    print(json.dumps({"learned": learned}, ensure_ascii=False))
    assert any(
        entry["source_message_id"] == str(message) and "APA" in entry["content"]
        for entry in learned
    )
    client.cookies.clear()
    interview_user = register(client)
    seed_learning_source(
        client,
        interview_user,
        content="受访者甲说：我以后都希望先听结论。这是访谈资料，不是我的偏好。",
    )
    assert client.app.state.memory_worker.run_once(extractor=extract)
    assert client.get("/api/memories").json()["items"] == []
