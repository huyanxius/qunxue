from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class AgentCitation:
    citation_id: str
    label: str
    kind: Literal["entry", "preview", "source", "theory", "directory"]
    excerpt: str | None = None
    knowledge_id: str | None = None
    source_id: str | None = None


@dataclass(frozen=True, slots=True)
class AgentMessage:
    message_id: UUID
    role: Literal["user", "assistant"]
    content: str
    citations: tuple[AgentCitation, ...] = ()
    sequence: int = 0
    created_at: datetime = field(default_factory=_now)


@dataclass(frozen=True, slots=True)
class AgentTurn:
    turn_id: UUID
    user_message: AgentMessage
    assistant_message: AgentMessage
    evidence_ids: frozenset[str]
    tool_summary: tuple[dict[str, object], ...] = ()

    @classmethod
    def create(
        cls,
        *,
        user_content: str,
        assistant_content: str,
        citations: tuple[AgentCitation, ...],
        evidence_ids: frozenset[str],
        sequence: int = 0,
        turn_id: UUID | None = None,
    ) -> "AgentTurn":
        if not user_content.strip() or not assistant_content.strip():
            raise ValueError("turn content must not be empty")
        if any(citation.citation_id not in evidence_ids for citation in citations):
            raise ValueError("citation must belong to current evidence")
        now = _now()
        resolved_turn_id = turn_id or uuid4()
        return cls(
            turn_id=resolved_turn_id,
            user_message=AgentMessage(
                message_id=uuid4(),
                role="user",
                content=user_content.strip(),
                sequence=sequence,
                created_at=now,
            ),
            assistant_message=AgentMessage(
                message_id=uuid4(),
                role="assistant",
                content=assistant_content.strip(),
                citations=citations,
                sequence=sequence + 1,
                created_at=now,
            ),
            evidence_ids=evidence_ids,
        )


@dataclass(frozen=True, slots=True)
class Conversation:
    conversation_id: UUID
    user_id: UUID
    title: str
    created_at: datetime
    updated_at: datetime
    turns: tuple[AgentTurn, ...] = ()


UserConversation = Conversation


@dataclass(frozen=True, slots=True)
class IdempotentTurn:
    turn_id: UUID


@dataclass(frozen=True, slots=True)
class AgentRun:
    run_id: UUID
    conversation_id: UUID
    user_id: UUID
    idempotency_key: str
    status: Literal["running", "completed", "failed", "interrupted"]
    knowledge_release_id: str | None = None
    turn_id: UUID | None = None
    tool_summary: tuple[dict[str, object], ...] = ()
