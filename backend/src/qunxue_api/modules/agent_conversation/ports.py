from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID

from qunxue_api.modules.agent_conversation.domain import (
    AgentRun,
    AgentTurn,
    Conversation,
    IdempotentTurn,
)


class AgentRelease(Protocol):
    knowledge_release_id: str


@dataclass(frozen=True, slots=True)
class AgentRuntimeIdentity:
    """Stable provider/model identity available before a runner invokes tools."""

    provider: str
    model: str


@dataclass(frozen=True, slots=True)
class AgentEvidence:
    citation_id: str
    label: str
    kind: str
    excerpt: str
    knowledge_id: str | None = None
    source_id: str | None = None


@dataclass(frozen=True, slots=True)
class AgentRunResult:
    answer: str
    citations: tuple[AgentEvidence, ...]
    release_id: str
    provider: str
    model: str


@dataclass(frozen=True, slots=True)
class AgentToolEvent:
    """One observable tool lifecycle event, never the model's hidden reasoning."""

    tool: str
    phase: Literal["started", "finished", "failed"]
    call_id: str
    input: Mapping[str, object] | None = None
    output: object | None = None
    detail: str | None = None
    error: str | None = None


class AgentToolContext(Protocol):
    release: AgentRelease
    evidence: Mapping[str, AgentEvidence]
    research_map_enabled: bool
    research_map: Mapping[str, object]

    def search_knowledge(self, query: str, *, limit: int = 5) -> list[dict[str, object]]: ...

    def enable_research_map(self, current: Mapping[str, object] | None = None) -> None: ...

    def update_research_map(
        self,
        *,
        nodes: Sequence[Mapping[str, object]] | None = None,
        relations: Sequence[Mapping[str, object]] | None = None,
        remove_node_ids: Sequence[str] | None = None,
        remove_relation_ids: Sequence[str] | None = None,
    ) -> dict[str, object]: ...


class SubjectAgentRunner(Protocol):
    runtime_identity: AgentRuntimeIdentity

    def run(
        self,
        *,
        prompt: str,
        conversation: str,
        tools: AgentToolContext,
    ) -> AgentRunResult: ...

    def run_stream(
        self,
        *,
        prompt: str,
        conversation: str,
        tools: AgentToolContext,
        on_delta: Callable[[str], None],
        on_tool_event: Callable[[AgentToolEvent], None] | None = None,
    ) -> AgentRunResult: ...


class ConversationRepository(Protocol):
    def commit(self) -> None: ...

    def create(self, conversation: Conversation) -> Conversation: ...

    def get(self, *, user_id: UUID, conversation_id: UUID) -> Conversation: ...

    def list(self, *, user_id: UUID) -> Sequence[Conversation]: ...

    def release_ids_by_turn(self, *, conversation_id: UUID) -> Mapping[UUID, str]: ...

    def append_turn(
        self,
        *,
        conversation: Conversation,
        turn: AgentTurn,
        idempotency_key: str,
    ) -> AgentTurn | IdempotentTurn: ...

    def start_run(self, run: AgentRun) -> AgentRun: ...

    def find_run(self, *, user_id: UUID, idempotency_key: str) -> AgentRun | None: ...

    def finish_run(
        self,
        *,
        run_id: UUID,
        status: str,
        error: str | None = None,
        turn_id: UUID | None = None,
        tool_summary: tuple[dict[str, object], ...] = (),
        provider: str | None = None,
        model: str | None = None,
    ) -> None: ...
