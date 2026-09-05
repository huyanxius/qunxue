"""A disposable reading aid, never a new memory or a conversation turn."""

import json
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from hashlib import sha256
from threading import Lock
from uuid import UUID

from qunxue_api.modules.agent_memory import Memory


class MemoryOverviewUnavailable(Exception):
    pass


class MemoryOverviewBusy(Exception):
    pass


def memory_overview_fingerprint(items: tuple[Memory, ...]) -> bytes:
    # Scope versions and list order also change after settings or no-op
    # edits. Only identity, origin and content change the summary's meaning.
    return sha256(
        json.dumps(
            [
                (str(m.memory_id), m.origin, m.content)
                for m in sorted(items, key=lambda m: m.memory_id)
            ],
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    ).digest()


@dataclass
class _OverviewEntry:
    fingerprint: bytes
    summary: str | None = None


class MemoryOverview:
    def __init__(self, generate: Callable[[tuple[Memory, ...]], str] | None = None):
        self.generate = generate
        self._lock = Lock()
        self._active: set[UUID] = set()
        self._cache: OrderedDict[tuple[UUID, UUID | None], _OverviewEntry] = OrderedDict()

    def invalidate(self, user_id: UUID, task_id: UUID | None) -> None:
        with self._lock:
            self._cache.pop((user_id, task_id), None)

    def summarize(
        self, user_id: UUID, task_id: UUID | None, version: int, items: tuple[Memory, ...]
    ) -> str:
        if not items:
            self.invalidate(user_id, task_id)
            return ""
        fingerprint = memory_overview_fingerprint(items)
        key = (user_id, task_id)
        with self._lock:
            cached = self._cache.get(key)
            if (
                cached is not None
                and cached.fingerprint == fingerprint
                and cached.summary is not None
            ):
                self._cache.move_to_end(key)
                return cached.summary
            if cached is not None and cached.fingerprint != fingerprint:
                del self._cache[key]
            if self.generate is None:
                raise MemoryOverviewUnavailable("记忆概览暂不可用，仍可查看和编辑下方记录。")
            if user_id in self._active or len(self._active) >= 4:
                raise MemoryOverviewBusy("正在整理记忆，请稍后重试。")
            self._active.add(user_id)
            entry = _OverviewEntry(fingerprint)
            self._cache[key] = entry
            self._cache.move_to_end(key)
            while len(self._cache) > 64:
                self._cache.popitem(last=False)
        try:
            summary = self.generate(items).strip()
            if not summary or len(summary) > 2000:
                raise ValueError("invalid_memory_overview")
            with self._lock:
                # A mutation can invalidate this placeholder while the model
                # runs. Its old result must never repopulate a cleared scope.
                if self._cache.get(key) is entry:
                    entry.summary = summary
            return summary
        except Exception as error:
            with self._lock:
                if self._cache.get(key) is entry:
                    del self._cache[key]
            raise MemoryOverviewUnavailable("概览暂未生成，可以先查看下方记忆记录。") from error
        finally:
            with self._lock:
                self._active.discard(user_id)
