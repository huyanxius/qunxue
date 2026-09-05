import hashlib
import re
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Literal
from uuid import UUID

from qunxue_api.modules.agent_memory import (
    MemoryConflict,
    MemoryNotFound,
    MemoryService,
    redact_sensitive,
)

_EXPLICIT_REQUEST = re.compile(
    r"(?:记住|记下|记着|记忆.{0,8}(?:改|删|更新)|(?:删除|修改|更新|清除).{0,16}记忆|忘记|忘掉|"
    r"\bremember\b|\bforget\b|(?:update|delete|save).{0,20}\bmemor(?:y|ies)\b)",
    re.IGNORECASE,
)


class AgentMemoryTools:
    """Identity and project are bound by the application, never supplied by the model."""

    def __init__(
        self,
        service_scope: Callable[[], AbstractContextManager[MemoryService]],
        *,
        user_id: UUID,
        task_id: UUID | None,
        conversation_id: UUID,
        prompt: str,
        run_id: UUID,
    ) -> None:
        self._service_scope = service_scope
        self._user_id, self._task_id = user_id, task_id
        self._conversation_id, self._run_id = conversation_id, run_id
        self._prompt = prompt
        self.can_write = bool(_EXPLICIT_REQUEST.search(prompt))
        self._reads = 0
        self._writes: dict[str, dict] = {}
        with service_scope() as memory:
            self.context = memory.context(user_id, task_id)

    def search(self, query: str) -> dict:
        if self._reads >= 1:
            return {"error": "memory_read_budget_exhausted"}
        self._reads += 1
        with self._service_scope() as memory:
            return {"items": memory.search(self._user_id, self._task_id, query)}

    def change(
        self,
        *,
        action: Literal["remember", "forget"],
        scope: Literal["user", "project"],
        key: str,
        content: str = "",
        expected_version: int | None = None,
    ) -> dict:
        if not self.can_write:
            return {"error": "explicit_request_required"}
        if scope == "project" and self._task_id is None:
            return {"error": "project_required"}
        task_id = self._task_id if scope == "project" else None
        operation = hashlib.sha256(
            str((self._run_id, action, scope, key, content, expected_version)).encode()
        ).hexdigest()
        if operation in self._writes:
            return self._writes[operation]
        if len(self._writes) >= 3:
            return {"error": "memory_write_budget_exhausted"}
        try:
            with self._service_scope() as memory:
                existing = next(
                    (m for m in memory.repository.list(self._user_id, task_id) if m.key == key),
                    None,
                )
                if existing and expected_version != existing.version:
                    return {
                        "error": "version_required",
                        "current_version": existing.version,
                        "content": existing.content,
                    }
                if action == "forget":
                    if existing is None:
                        return {"error": "memory_not_found"}
                    memory.repository.delete(self._user_id, existing.memory_id, expected_version)
                    result = {"forgotten": True, "key": key}
                else:
                    saved = memory.save(
                        user_id=self._user_id,
                        task_id=task_id,
                        key=key,
                        content=content,
                        origin="explicit",
                        idempotency_key=operation,
                        memory_id=existing.memory_id if existing else None,
                        expected_version=expected_version,
                        source_conversation_id=self._conversation_id,
                        source_quote=redact_sensitive(self._prompt)[:1000],
                    )
                    result = {"saved": True, "key": saved.key, "version": saved.version}
            self._writes[operation] = result
            return result
        except (MemoryConflict, MemoryNotFound, ValueError) as error:
            return {"error": "memory_change_rejected", "message": str(error)}
