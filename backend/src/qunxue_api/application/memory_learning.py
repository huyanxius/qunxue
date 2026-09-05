import logging
from collections.abc import Callable
from contextlib import AbstractContextManager

from qunxue_api.modules.agent_memory import LearningBatch, MemoryCandidate, MemoryLearningRepository

logger = logging.getLogger(__name__)
MemoryExtractor = Callable[[LearningBatch], tuple[tuple[MemoryCandidate, ...], int, int]]


class MemoryLearningWorker:
    """One bounded extraction, then deterministic merge; no model call holds a DB transaction."""

    def __init__(
        self,
        repository_scope: Callable[[], AbstractContextManager[MemoryLearningRepository]],
        *,
        extractor: MemoryExtractor | None = None,
        idle_seconds: int = 600,
        daily_calls: int = 8,
        daily_tokens: int = 64000,
    ) -> None:
        self._repository_scope = repository_scope
        self._extractor = extractor
        self._idle_seconds = idle_seconds
        self._daily_calls = daily_calls
        self._daily_tokens = daily_tokens

    def run_once(self, *, extractor: MemoryExtractor | None = None) -> bool:
        extract = extractor or self._extractor
        if extract is None:
            return False
        with self._repository_scope() as repository:
            batch = repository.claim(
                idle_seconds=self._idle_seconds,
                daily_calls=self._daily_calls,
                daily_tokens=self._daily_tokens,
            )
        if batch is None:
            return False
        try:
            candidates, input_tokens, output_tokens = extract(batch)
            with self._repository_scope() as repository:
                repository.complete(batch, candidates, input_tokens, output_tokens)
        except Exception:
            # Store a stable error code, never prompts, credentials or provider error bodies.
            logger.warning("Memory learning attempt failed; the conversation remains usable.")
            with self._repository_scope() as repository:
                repository.failed(batch)
        return True
