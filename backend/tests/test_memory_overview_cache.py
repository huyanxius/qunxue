from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

import pytest

import qunxue_api.application.memory_overview as overview_module
from qunxue_api.application.memory_overview import (
    MemoryOverview,
    MemoryOverviewBusy,
    MemoryOverviewUnavailable,
)
from qunxue_api.modules.agent_memory import Memory


def memory():
    now = datetime.now(UTC)
    return Memory(uuid4(), uuid4(), None, "language", "使用中文。", "manual", 1, now, now)


def numbered_generator():
    summaries = iter(f"概览 {number}" for number in range(100))
    return lambda items: next(summaries)


def test_same_contents_reuse_overview_after_settings_changes():
    item = memory()
    service = MemoryOverview(numbered_generator())

    assert service.summarize(item.user_id, None, 1, (item,)) == "概览 0"
    assert service.summarize(item.user_id, None, 2, (item,)) == "概览 0"


def test_same_contents_do_not_expire_after_five_minutes(monkeypatch):
    now = 0
    monkeypatch.setattr(overview_module, "monotonic", lambda: now, raising=False)
    item = memory()
    service = MemoryOverview(numbered_generator())

    assert service.summarize(item.user_id, None, 1, (item,)) == "概览 0"
    now = 3600
    assert service.summarize(item.user_id, None, 1, (item,)) == "概览 0"


def test_same_contents_reuse_overview_when_record_order_changes():
    item = memory()
    second = replace(item, memory_id=uuid4(), content="先开放编码。")
    service = MemoryOverview(numbered_generator())

    assert service.summarize(item.user_id, None, 1, (item, second)) == "概览 0"
    assert service.summarize(item.user_id, None, 2, (second, item)) == "概览 0"


@pytest.mark.parametrize(
    "change",
    [{"content": "保留原文。"}, {"origin": "learned"}, {"memory_id": uuid4()}],
)
def test_changed_summary_input_does_not_reuse_old_content(change):
    item = memory()
    service = MemoryOverview(numbered_generator())

    assert service.summarize(item.user_id, None, 1, (item,)) == "概览 0"
    changed = replace(item, **change)
    assert service.summarize(item.user_id, None, 1, (changed,)) == "概览 1"


def test_overview_cache_is_isolated_between_users_and_projects():
    item = memory()
    service = MemoryOverview(numbered_generator())
    other_user, project = uuid4(), uuid4()

    assert service.summarize(item.user_id, None, 1, (item,)) == "概览 0"
    assert service.summarize(other_user, None, 1, (replace(item, user_id=other_user),)) == "概览 1"
    project_item = replace(item, task_id=project)
    assert service.summarize(item.user_id, project, 1, (project_item,)) == "概览 2"
    assert service.summarize(item.user_id, None, 2, (item,)) == "概览 0"


def test_empty_scope_discards_previous_overview():
    item = memory()
    service = MemoryOverview(numbered_generator())

    assert service.summarize(item.user_id, None, 1, (item,)) == "概览 0"
    assert service.summarize(item.user_id, None, 2, ()) == ""
    assert service.summarize(item.user_id, None, 1, (item,)) == "概览 1"


def test_invalidate_discards_only_the_changed_scope():
    item = memory()
    project = uuid4()
    service = MemoryOverview(numbered_generator())

    assert service.summarize(item.user_id, None, 1, (item,)) == "概览 0"
    assert service.summarize(item.user_id, project, 1, (item,)) == "概览 1"
    service.invalidate(item.user_id, None)
    assert service.summarize(item.user_id, None, 1, (item,)) == "概览 2"
    assert service.summarize(item.user_id, project, 2, (item,)) == "概览 1"


@pytest.mark.parametrize("clear_scope", ["invalidate", "empty"])
def test_scope_cleared_during_generation_cannot_restore_old_cache(clear_scope):
    item = memory()

    def generate(items):
        if clear_scope == "invalidate":
            service.invalidate(item.user_id, None)
        else:
            assert service.summarize(item.user_id, None, 2, ()) == ""
        return "删除前的旧概览"

    service = MemoryOverview(generate)
    service.summarize(item.user_id, None, 1, (item,))
    service.generate = lambda items: "重新生成的概览"
    assert service.summarize(item.user_id, None, 1, (item,)) == "重新生成的概览"


def test_failed_generation_does_not_keep_stale_overview_or_busy_state():
    item = memory()
    service = MemoryOverview(numbered_generator())
    assert service.summarize(item.user_id, None, 1, (item,)) == "概览 0"

    def fail(items):
        raise RuntimeError("model unavailable")

    service.generate = fail
    changed = replace(item, content="保留原文。")
    with pytest.raises(MemoryOverviewUnavailable):
        service.summarize(item.user_id, None, 2, (changed,))
    service.generate = lambda items: "恢复后的概览"
    assert service.summarize(item.user_id, None, 2, (changed,)) == "恢复后的概览"
    assert service.summarize(item.user_id, None, 1, (item,)) == "恢复后的概览"


def test_changed_snapshot_during_generation_cannot_restore_old_cache():
    item = memory()
    changed = replace(item, content="保留原文。")

    def generate(items):
        with pytest.raises(MemoryOverviewBusy):
            service.summarize(item.user_id, None, 2, (changed,))
        return "旧概览"

    service = MemoryOverview(generate)
    service.summarize(item.user_id, None, 1, (item,))
    service.generate = lambda items: "新概览"
    assert service.summarize(item.user_id, None, 1, (item,)) == "新概览"


def test_cache_evicts_least_recently_used_scopes():
    item = memory()
    users = [uuid4() for _ in range(65)]
    service = MemoryOverview(numbered_generator())
    for number, user in enumerate(users[:64]):
        assert service.summarize(user, None, 1, (item,)) == f"概览 {number}"

    assert service.summarize(users[0], None, 2, (item,)) == "概览 0"
    assert service.summarize(users[64], None, 1, (item,)) == "概览 64"
    assert service.summarize(users[0], None, 2, (item,)) == "概览 0"
    assert service.summarize(users[1], None, 1, (item,)) == "概览 65"


def test_generation_limits_one_per_user_and_four_in_total():
    items = [memory() for _ in range(5)]

    def generate(current):
        number = items.index(current[0])
        with pytest.raises(MemoryOverviewBusy):
            service.summarize(current[0].user_id, uuid4(), 1, current)
        if number < 3:
            next_item = items[number + 1]
            return service.summarize(next_item.user_id, None, 1, (next_item,))
        if number == 3:
            with pytest.raises(MemoryOverviewBusy):
                service.summarize(items[4].user_id, None, 1, (items[4],))
        return "生成完成"

    service = MemoryOverview(generate)
    assert service.summarize(items[0].user_id, None, 1, (items[0],)) == "生成完成"
    assert service.summarize(items[4].user_id, None, 1, (items[4],)) == "生成完成"
