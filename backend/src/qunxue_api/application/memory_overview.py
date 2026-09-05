"""A disposable reading aid, never a new memory or a conversation turn."""

from collections import OrderedDict
from collections.abc import Callable
from threading import Lock
from time import monotonic
from uuid import UUID

from qunxue_api.modules.agent_memory import Memory


class MemoryOverviewUnavailable(Exception):
    pass


class MemoryOverviewBusy(Exception):
    pass


class MemoryOverview:
    def __init__(self, generate: Callable[[tuple[Memory, ...]], str] | None = None):
        self.generate = generate
        self._lock = Lock()
        self._active: set[UUID] = set()
        self._cache: OrderedDict[tuple, tuple[float, str]] = OrderedDict()

    def summarize(
        self, user_id: UUID, task_id: UUID | None, version: int, items: tuple[Memory, ...]
    ) -> str:
        if not items:
            return ""
        if self.generate is None:
            raise MemoryOverviewUnavailable("记忆概览暂不可用，仍可查看和编辑下方记录。")
        key = (user_id, task_id, version)
        with self._lock:
            now = monotonic()
            self._cache = OrderedDict((k, v) for k, v in self._cache.items() if now - v[0] < 300)
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key][1]
            if user_id in self._active or len(self._active) >= 4:
                raise MemoryOverviewBusy("正在整理记忆，请稍后重试。")
            self._active.add(user_id)
        try:
            summary = self.generate(items).strip()
            if not summary or len(summary) > 2000:
                raise ValueError("invalid_memory_overview")
            with self._lock:
                # Keep only the latest cached version of this scope.
                for old in list(self._cache):
                    if old[:2] == key[:2]:
                        del self._cache[old]
                self._cache[key] = (monotonic(), summary)
                while len(self._cache) > 64:
                    self._cache.popitem(last=False)
            return summary
        except Exception as error:
            raise MemoryOverviewUnavailable("概览暂未生成，可以先查看下方记忆记录。") from error
        finally:
            with self._lock:
                self._active.discard(user_id)
