from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
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
    source_kind: str | None = None
    material_id: str | None = None
    parse_id: str | None = None
    segment_id: str | None = None
    locator: dict[str, object] | None = None
    deleted: bool = False


@dataclass(frozen=True, slots=True)
class AgentRunResult:
    answer: str
    citations: tuple[AgentEvidence, ...]
    release_id: str
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0


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


@dataclass(frozen=True, slots=True)
class AgentResearchEvent:
    """Model-authored research UX state exposed as a safe, structured event."""

    kind: Literal["ask", "plan", "step", "result"]
    payload: Mapping[str, object]


class AgentToolContext(Protocol):
    release: AgentRelease
    evidence: Mapping[str, AgentEvidence]
    research_map_enabled: bool
    research_map: Mapping[str, object]
    web_search_enabled: bool

    def search_knowledge(self, query: str, *, limit: int = 5) -> list[dict[str, object]]: ...

    def search_research_materials(
        self, query: str, *, limit: int = 5
    ) -> list[dict[str, object]]: ...

    def enable_web_search(self) -> None: ...

    def search_web(self, query: str, *, limit: int = 5) -> list[dict[str, object]]: ...

    def read_web_page(self, url: str) -> dict[str, object]: ...

    def read_research_material_context(
        self,
        material_id: str,
        segment_id: str | None = None,
        *,
        parse_id: str | None = None,
        before: int = 2,
        after: int = 2,
    ) -> dict[str, object]: ...

    def select_evidence(self, citation_ids: Sequence[str]) -> tuple[str, ...]: ...

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
        conversation: Sequence[AgentTurn],
        tools: AgentToolContext,
    ) -> AgentRunResult: ...

    def run_stream(
        self,
        *,
        prompt: str,
        conversation: Sequence[AgentTurn],
        tools: AgentToolContext,
        on_delta: Callable[[str], None],
        on_tool_event: Callable[[AgentToolEvent], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> AgentRunResult: ...


class ConversationRepository(Protocol):
    def commit(self) -> None: ...

    def get_research_task_id(self, *, user_id: UUID, conversation_id: UUID) -> UUID | None: ...

    def link_research_task(
        self, *, user_id: UUID, conversation_id: UUID, task_id: UUID
    ) -> None: ...

    def create(self, conversation: Conversation) -> Conversation: ...

    def get(self, *, user_id: UUID, conversation_id: UUID) -> Conversation: ...

    def list(self, *, user_id: UUID) -> Sequence[Conversation]: ...

    def rename(
        self,
        *,
        user_id: UUID,
        conversation_id: UUID,
        title: str,
        updated_at: datetime,
    ) -> Conversation: ...

    def edit_canvas_node(
        self,
        *,
        user_id: UUID,
        conversation_id: UUID,
        node_id: str,
        title: str,
        summary: str,
        expected_title: str,
        expected_summary: str | None,
        expected_version: int,
    ) -> Conversation: ...

    def delete(self, *, user_id: UUID, conversation_id: UUID) -> None: ...

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

    def find_run_by_id(self, *, user_id: UUID, run_id: UUID) -> AgentRun | None: ...

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
