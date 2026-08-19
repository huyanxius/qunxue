from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class AgentCitationResponse(BaseModel):
    citation_id: str
    label: str
    kind: str
    excerpt: str | None = None
    knowledge_id: str | None = None
    source_id: str | None = None


class AgentMessageResponse(BaseModel):
    message_id: UUID
    role: str
    content: str
    citations: list[AgentCitationResponse] = Field(default_factory=list)
    sequence: int
    created_at: datetime


class AgentToolTraceResponse(BaseModel):
    tool: str
    phase: Literal["started", "finished", "failed"]
    call_id: str
    input: dict[str, object] | None = None
    output: object | None = None
    detail: str | None = None
    error: str | None = None


class AgentTurnResponse(BaseModel):
    turn_id: UUID
    user: AgentMessageResponse
    assistant: AgentMessageResponse
    tool_traces: list[AgentToolTraceResponse] = Field(default_factory=list)
    knowledge_release_id: str | None = None
    canvas_patches: list[dict[str, object]] = Field(default_factory=list)


class AgentConversationSummaryResponse(BaseModel):
    conversation_id: UUID
    title: str
    updated_at: datetime
    turn_count: int


class AgentConversationResponse(AgentConversationSummaryResponse):
    created_at: datetime
    turns: list[AgentTurnResponse]
    research_map: dict[str, object] = Field(default_factory=dict)


class AgentConversationListResponse(BaseModel):
    items: list[AgentConversationSummaryResponse]


class AgentTurnRequest(BaseModel):
    conversation_id: UUID | None = None
    message: str = Field(min_length=1, max_length=12000)
    workspace: Literal["agent", "research"] = "agent"
