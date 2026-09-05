import json
import re
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from test_agent_memory import register, save

from qunxue_api.modules.agent_memory import Memory, render_context


def memory_entry(content, *, key="method", origin="manual", updated_at=None, user_id=None):
    now = updated_at or datetime.now(UTC)
    return Memory(
        memory_id=uuid4(),
        user_id=user_id or uuid4(),
        task_id=None,
        key=key,
        content=content,
        origin=origin,
        version=1,
        created_at=now,
        updated_at=now,
    )


def test_manual_memory_stores_full_chinese_content_independently_of_context_budget(plain_client):
    register(plain_client)
    content = "研" * 666 + "ab"
    first = save(plain_client, "first", content)
    second = save(plain_client, "second", content)
    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert [item["content"] for item in plain_client.get("/api/memories").json()["items"]] == [
        content,
        content,
    ]
    assert save(plain_client, "oversize", content + "x").status_code == 422


def test_memory_count_limit_allows_editing_existing_manual_and_explicit_entries(plain_client):
    user_id = UUID(register(plain_client))
    with plain_client.app.state.memory_service_scope() as service:
        entries = [
            service.save(
                user_id=user_id,
                task_id=None,
                key=f"note.{index}",
                content="研" * 666 + "ab",
                origin="manual" if index % 2 else "explicit",
                idempotency_key=str(uuid4()),
            )
            for index in range(100)
        ]
        assert len(service.repository.list(user_id, None)) == 100
        with pytest.raises(ValueError, match="条目已达上限"):
            service.save(
                user_id=user_id,
                task_id=None,
                key="overflow",
                content="new entry",
                origin="manual",
                idempotency_key=str(uuid4()),
            )
        updated = service.save(
            user_id=user_id,
            task_id=None,
            key=entries[0].key,
            content="完整保留人工修正",
            origin="manual",
            idempotency_key=str(uuid4()),
            memory_id=entries[0].memory_id,
            expected_version=entries[0].version,
        )
        assert updated.content == "完整保留人工修正"
        assert len(service.repository.list(user_id, None)) == 100


def test_context_omits_long_content_whole_and_marks_more_memory_available():
    content = "长篇研究要求" * 100
    context = render_context((memory_entry(content),))
    assert len(context.encode("utf-8")) <= 1200
    assert "长篇研究要求" not in context
    assert re.search(r"\bsearch\b", context, re.IGNORECASE)


def test_context_keeps_human_entries_before_newer_learned_memory_and_budgets_notice():
    now = datetime.now(UTC)
    entries = (
        memory_entry("推断" * 120, origin="learned", updated_at=now),
        memory_entry("人工要求" * 28, key="user_rule", updated_at=now - timedelta(days=2)),
        replace(
            memory_entry(
                "项目要求" * 28,
                key="project_rule",
                origin="explicit",
                updated_at=now - timedelta(days=1),
            ),
            task_id=uuid4(),
        ),
    )
    context = render_context(entries)
    assert entries[1].content in context
    assert entries[2].content in context
    assert "推断" not in context
    assert re.search(r"\bsearch\b", context, re.IGNORECASE)
    assert len(context.encode("utf-8")) <= 1200


def test_context_without_omissions_does_not_request_additional_search():
    context = render_context((memory_entry("简洁回答"),))
    assert "简洁回答" in context
    assert not re.search(r"\bsearch\b", context, re.IGNORECASE)


@pytest.mark.parametrize(
    "content", ["研" * 666 + "ab", "a" + "\x01" * 1999], ids=["chinese", "escaped_controls"]
)
def test_search_returns_maximum_legal_content_in_full(plain_client, content):
    user_id = UUID(register(plain_client))
    with plain_client.app.state.memory_service_scope() as service:
        service.repository.lock_scope(service.repository.scope(user_id, None))
        entry = memory_entry(content, key="full." + "x" * 59, origin="learned", user_id=user_id)
        service.repository.store(entry)
        results = service.search(user_id, None, "full")
        assert len(results) == 1
        assert results[0]["content"] == content
        assert results[0]["key"] == entry.key


@pytest.mark.parametrize(
    "content", ["a" * 2000, "a" + "\x01" * 449], ids=["long_notes", "escaped_controls"]
)
def test_search_scans_past_unfitting_matches_and_counts_serialized_json(plain_client, content):
    user_id = UUID(register(plain_client))
    now = datetime.now(UTC)
    with plain_client.app.state.memory_service_scope() as service:
        service.repository.lock_scope(service.repository.scope(user_id, None))
        for index in range(5):
            service.repository.store(
                memory_entry(
                    content,
                    key=f"match.{index}",
                    origin="learned",
                    user_id=user_id,
                    updated_at=now - timedelta(seconds=index),
                )
            )
        service.repository.store(
            memory_entry(
                "简短补充",
                key="match.short",
                origin="learned",
                user_id=user_id,
                updated_at=now - timedelta(seconds=6),
            )
        )
        results = service.search(user_id, None, "match")
        assert [item["key"] for item in results] == ["match.0", "match.short"]
        encoded = json.dumps({"items": results}, ensure_ascii=False, separators=(",", ":"))
        assert len(encoded.encode("utf-8")) <= 4096


def test_search_returns_only_one_entry_when_json_escaping_exceeds_normal_budget(plain_client):
    user_id = UUID(register(plain_client))
    now = datetime.now(UTC)
    content = "a" + "\x01" * 1999
    with plain_client.app.state.memory_service_scope() as service:
        service.repository.lock_scope(service.repository.scope(user_id, None))
        service.repository.store(
            memory_entry(content, key="match.long", user_id=user_id, updated_at=now)
        )
        service.repository.store(
            memory_entry(
                "简短补充",
                key="match.short",
                user_id=user_id,
                updated_at=now - timedelta(seconds=1),
            )
        )
        results = service.search(user_id, None, "match")
        assert [item["content"] for item in results] == [content]
        encoded = json.dumps({"items": results}, ensure_ascii=False, separators=(",", ":"))
        assert 4096 < len(encoded.encode("utf-8")) <= 12512


def test_search_stops_at_five_returned_entries(plain_client):
    user_id = UUID(register(plain_client))
    with plain_client.app.state.memory_service_scope() as service:
        service.repository.lock_scope(service.repository.scope(user_id, None))
        for index in range(6):
            service.repository.store(
                memory_entry("访谈", key=f"match.{index}", origin="learned", user_id=user_id)
            )
        assert len(service.search(user_id, None, "match")) == 5
