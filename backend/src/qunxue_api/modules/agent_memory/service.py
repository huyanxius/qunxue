import json
from uuid import UUID

from .domain import (
    SEARCH_BUDGET,
    SEARCH_SINGLE_BUDGET,
    Memory,
    context_cost,
    render_context,
    validate_content,
)
from .ports import MemoryRepository


class MemoryService:
    def __init__(self, repository: MemoryRepository) -> None:
        self.repository = repository

    def context(self, user_id: UUID, task_id: UUID | None) -> str:
        return render_context(self.available(user_id, task_id))

    def available(self, user_id: UUID, task_id: UUID | None) -> tuple[Memory, ...]:
        result = ()
        for scope in (None, task_id) if task_id else (None,):
            if self.repository.scope(user_id, scope).use_memory:
                result += self.repository.list(user_id, scope)
        return result

    def search(self, user_id: UUID, task_id: UUID | None, query: str) -> list[dict]:
        words = query.strip().casefold().split()
        if not words:
            return []
        matches = [
            m
            for m in self.available(user_id, task_id)
            if any(word in (m.key + " " + m.content).casefold() for word in words)
        ]
        result: list[dict] = []
        for item in matches:
            value = {
                "memory_id": str(item.memory_id),
                "key": item.key,
                "content": item.content,
                "version": item.version,
                "scope": "project" if item.task_id else "user",
                "origin": item.origin,
            }
            cost = context_cost(
                json.dumps({"items": [*result, value]}, ensure_ascii=False, separators=(",", ":"))
            )
            if cost <= SEARCH_BUDGET:
                result.append(value)
                if len(result) == 5:
                    break
            elif not result and cost <= SEARCH_SINGLE_BUDGET:
                # Never make a valid note unreadable because JSON escaping expands
                # it. A larger single result cannot also grow into a multi-note load.
                return [value]
        return result

    def save(self, **kwargs) -> Memory:
        kwargs["key"], kwargs["content"] = validate_content(kwargs["key"], kwargs["content"])
        return self.repository.save(**kwargs)
