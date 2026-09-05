from typing import Protocol
from uuid import UUID

from .domain import LearningBatch, Memory, MemoryCandidate, MemoryOrigin, MemoryScope


class MemoryRepository(Protocol):
    def scope(self, user_id: UUID, task_id: UUID | None) -> MemoryScope: ...

    def list(self, user_id: UUID, task_id: UUID | None) -> tuple[Memory, ...]: ...

    def get(self, user_id: UUID, memory_id: UUID) -> Memory: ...

    def save(
        self,
        *,
        user_id: UUID,
        task_id: UUID | None,
        key: str,
        content: str,
        origin: MemoryOrigin,
        idempotency_key: str,
        memory_id: UUID | None = None,
        expected_version: int | None = None,
        source_conversation_id: UUID | None = None,
        source_quote: str | None = None,
    ) -> Memory: ...

    def delete(self, user_id: UUID, memory_id: UUID, expected_version: int) -> None: ...

    def revisions(self, user_id: UUID, memory_id: UUID) -> tuple[Memory, ...]: ...

    def configure(
        self,
        user_id: UUID,
        task_id: UUID | None,
        *,
        expected_version: int,
        use_memory: bool,
        learn_memory: bool,
    ) -> MemoryScope: ...


class MemoryLearningRepository(Protocol):
    def claim(
        self, *, idle_seconds: int, daily_calls: int, daily_tokens: int
    ) -> LearningBatch | None: ...

    def complete(
        self,
        batch: LearningBatch,
        candidates: tuple[MemoryCandidate, ...],
        input_tokens: int,
        output_tokens: int,
    ) -> None: ...

    def failed(self, batch: LearningBatch) -> None: ...
