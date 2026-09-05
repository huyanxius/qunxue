from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from test_agent_memory import register, save, seed_learning_source

from qunxue_api.adapters.sqlite.agent_conversation_model import AgentMessageRow
from qunxue_api.adapters.sqlite.agent_memory_model import MemoryJobRow, MemoryUsageRow
from qunxue_api.adapters.sqlite.agent_memory_repository import SqliteMemoryRepository
from qunxue_api.adapters.sqlite.memory_learning_repository import SqliteMemoryLearningRepository
from qunxue_api.modules.agent_memory import MemoryCandidate, MemoryConflict


def test_delete_rechecks_version_after_concurrent_human_edit(plain_client, monkeypatch):
    client = plain_client
    user_id = UUID(register(client))
    entry = save(client).json()
    memory_id = UUID(entry["memory_id"])
    with pytest.raises(MemoryConflict), client.app.state.database.session() as session:
        repository = SqliteMemoryRepository(session)
        original_get = repository.get
        edited = False

        def interleaved_get(*args):
            nonlocal edited
            result = original_get(*args)
            if not edited:
                edited = True
                response = client.patch(
                    f"/api/memories/{memory_id}",
                    headers={"Idempotency-Key": str(uuid4())},
                    json={"content": "最新人工决定", "expected_version": 1},
                )
                assert response.status_code == 200
            return result

        monkeypatch.setattr(repository, "get", interleaved_get)
        repository.delete(user_id, memory_id, 1)
    assert client.get(f"/api/memories/{memory_id}").json()["content"] == "最新人工决定"


def test_exhausted_user_does_not_starve_other_users(plain_client):
    client = plain_client
    exhausted_user = register(client)
    for _ in range(32):
        seed_learning_source(client, exhausted_user)
    with client.app.state.database.session() as session:
        session.add(
            MemoryUsageRow(
                user_id=exhausted_user,
                day=datetime.now(UTC).date().isoformat(),
                calls=8,
                input_tokens=0,
                output_tokens=0,
                budget_tokens=64000,
            )
        )
    client.cookies.clear()
    register_user = register(client)
    _, message = seed_learning_source(client, register_user)
    seen = []

    def extract(batch):
        seen.append(str(batch.user_id))
        return (
            (MemoryCandidate("user", "style", "中文简洁回答", message, "以后请用中文简洁回答"),),
            10,
            10,
        )

    assert client.app.state.memory_worker.run_once(extractor=extract)
    assert seen == [register_user]


def test_long_conversation_stops_retrying_same_failed_batch(plain_client):
    client = plain_client
    user_id = register(client)
    conversation, _ = seed_learning_source(client, user_id)
    now = datetime.now(UTC)
    with client.app.state.database.session() as session:
        for sequence in range(1, 17):
            session.add(
                AgentMessageRow(
                    message_id=str(uuid4()),
                    conversation_id=str(conversation),
                    turn_id=str(uuid4()),
                    role="user",
                    content="以后请用中文简洁回答",
                    sequence=sequence,
                    created_at=now - timedelta(hours=1),
                )
            )
    calls = []

    def fail(batch):
        calls.append(batch.through_sequence)
        raise ValueError("model unavailable")

    for _ in range(3):
        assert client.app.state.memory_worker.run_once(extractor=fail)
        with client.app.state.database.session() as session:
            session.get(MemoryJobRow, str(conversation)).retry_after = now - timedelta(minutes=1)
            usage = session.get(MemoryUsageRow, (user_id, now.date().isoformat()))
            usage.budget_tokens = 0
    assert not client.app.state.memory_worker.run_once(extractor=fail)
    assert calls == [15, 15, 15]


def test_old_conversation_cannot_replace_newer_learned_preference(plain_client):
    client = plain_client
    user_id = register(client)
    _, recent_message = seed_learning_source(client, user_id, content="以后用简短回答")
    _, old_message = seed_learning_source(client, user_id, content="以后用详细回答")
    with client.app.state.database.session() as session:
        session.get(AgentMessageRow, str(old_message)).created_at = datetime.now(UTC) - timedelta(
            days=1
        )

    def extract(batch):
        source = batch.sources[0]
        return (
            (MemoryCandidate("user", "style", source.content, source.message_id, source.content),),
            10,
            10,
        )

    assert client.app.state.memory_worker.run_once(extractor=extract)
    assert client.app.state.memory_worker.run_once(extractor=extract)
    entry = client.get("/api/memories").json()["items"][0]
    assert entry["source_message_id"] == str(recent_message)
    assert entry["content"] == "以后用简短回答"


def test_same_content_confirmation_advances_source_watermark(plain_client):
    client = plain_client
    user_id = register(client)
    now = datetime.now(UTC)
    messages = []
    for days, content in [(3, "简短回答"), (1, "简短回答"), (2, "详细回答")]:
        _, message = seed_learning_source(client, user_id, content=content)
        with client.app.state.database.session() as session:
            session.get(AgentMessageRow, str(message)).created_at = now - timedelta(days=days)
        messages.append(message)

    def extract(batch):
        source = batch.sources[0]
        return (
            (MemoryCandidate("user", "style", source.content, source.message_id, source.content),),
            10,
            10,
        )

    for _ in messages:
        assert client.app.state.memory_worker.run_once(extractor=extract)
    entry = client.get("/api/memories").json()["items"][0]
    assert entry["content"] == "简短回答"
    assert entry["source_message_id"] == str(messages[1])


def test_one_batch_uses_latest_source_for_duplicate_keys(plain_client):
    client = plain_client
    user_id = register(client)
    conversation, _ = seed_learning_source(client, user_id, content="简短回答")
    with client.app.state.database.session() as session:
        session.add(
            AgentMessageRow(
                message_id=str(uuid4()),
                conversation_id=str(conversation),
                turn_id=str(uuid4()),
                role="user",
                content="详细回答",
                sequence=2,
                created_at=datetime.now(UTC) - timedelta(minutes=30),
            )
        )

    def extract(batch):
        return (
            tuple(
                MemoryCandidate("user", "style", s.content, s.message_id, s.content)
                for s in batch.sources
            ),
            10,
            10,
        )

    assert client.app.state.memory_worker.run_once(extractor=extract)
    assert client.get("/api/memories").json()["items"][0]["content"] == "详细回答"


def test_expired_lease_is_recoverable_and_old_worker_cannot_commit(plain_client):
    client = plain_client
    user_id = register(client)
    conversation, message = seed_learning_source(client, user_id)

    def claim():
        with client.app.state.database.session() as session:
            return SqliteMemoryLearningRepository(session).claim(
                idle_seconds=600,
                daily_calls=8,
                daily_tokens=64000,
            )

    first = claim()
    assert first is not None
    assert claim() is None
    with client.app.state.database.session() as session:
        session.get(MemoryJobRow, str(conversation)).lease_until = datetime.now(UTC) - timedelta(
            seconds=1
        )
    second = claim()
    assert second is not None and second.lease_token != first.lease_token
    candidate = (MemoryCandidate("user", "style", "中文简洁回答", message, "以后请用中文简洁回答"),)
    with client.app.state.database.session() as session:
        SqliteMemoryLearningRepository(session).complete(first, candidate, 10, 10)
    assert client.get("/api/memories").json()["items"] == []
    with client.app.state.database.session() as session:
        SqliteMemoryLearningRepository(session).complete(second, candidate, 10, 10)
    assert len(client.get("/api/memories").json()["items"]) == 1
