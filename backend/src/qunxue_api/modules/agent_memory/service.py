from uuid import UUID

from .domain import DETAIL_BUDGET, Memory, context_cost, render_context, validate_content
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
        used = 0
        for item in matches[:5]:
            value = {
                "memory_id": str(item.memory_id),
                "key": item.key,
                "content": item.content,
                "version": item.version,
                "scope": "project" if item.task_id else "user",
                "origin": item.origin,
            }
            cost = context_cost(str(value))
            if used + cost <= DETAIL_BUDGET:
                result.append(value)
                used += cost
        return result

    def save(self, **kwargs) -> Memory:
        kwargs["key"], kwargs["content"] = validate_content(kwargs["key"], kwargs["content"])
        return self.repository.save(**kwargs)
