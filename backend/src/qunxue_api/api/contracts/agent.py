from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, StringConstraints

from qunxue_api.api.contracts.research_tasks import ResearchTaskNavigationResponse
from qunxue_api.modules.research_intake import ResearchStartProposal


class AgentCitationResponse(BaseModel):
    citation_id: str
    label: str
    kind: str
    excerpt: str | None = None
    knowledge_id: str | None = None
    source_id: str | None = None
    source_kind: str | None = None
    material_id: str | None = None
    parse_id: str | None = None
    segment_id: str | None = None
    locator: dict[str, object] | None = None
    deleted: bool = False


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


class AgentResearchMapNodeResponse(BaseModel):
    id: str
    kind: Literal["question", "theory", "claim", "evidence", "gap", "synthesis"]
    title: str
    summary: str | None = None
    status: Literal["developing", "grounded", "open", "verified", "challenged", "complete"]
    citation_ids: list[str]


class AgentResearchMapRelationResponse(BaseModel):
    id: str
    source: str
    target: str
    relation: Literal["explains", "supports", "challenges", "derives", "refines"]
    label: str | None = None


class AgentResearchMapPatchResponse(BaseModel):
    schema_version: Literal[1]
    nodes: list[AgentResearchMapNodeResponse]
    relations: list[AgentResearchMapRelationResponse]
    remove_node_ids: list[str]
    remove_relation_ids: list[str]


class AgentResearchMapResponse(BaseModel):
    schema_version: Literal[1]
    nodes: list[AgentResearchMapNodeResponse]
    relations: list[AgentResearchMapRelationResponse]


class AgentTurnResponse(BaseModel):
    turn_id: UUID
    user: AgentMessageResponse
    assistant: AgentMessageResponse
    tool_traces: list[AgentToolTraceResponse] = Field(default_factory=list)
    knowledge_release_id: str | None = None
    canvas_patches: list[AgentResearchMapPatchResponse] = Field(default_factory=list)


class AgentConversationSummaryResponse(BaseModel):
    conversation_id: UUID
    title: str
    updated_at: datetime
    turn_count: int


class AgentConversationResponse(AgentConversationSummaryResponse):
    created_at: datetime
    turns: list[AgentTurnResponse]
    research_map: AgentResearchMapResponse


class AgentConversationListResponse(BaseModel):
    items: list[AgentConversationSummaryResponse]


class AgentConversationUpdateRequest(BaseModel):
    title: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=120),
    ]


class AgentTurnRequest(BaseModel):
    conversation_id: UUID | None = None
    message: str = Field(min_length=1, max_length=12000)
    workspace: Literal["agent", "research"] = "agent"
    web_search: bool = False
    task_id: UUID | None = None
    document_id: UUID | None = None
    section_id: str | None = None
    document_version: int | None = None
    theory_plan_id: UUID | None = None
    mode: Literal["standard", "deep_research"] = "standard"
    deep_research_run_id: UUID | None = None
    deep_research_action: Literal["clarify", "confirm"] | None = None
    deep_research_selection: str | None = Field(default=None, max_length=4000)


class ResearchStartProposalResponse(BaseModel):
    proposal_id: UUID
    conversation_id: UUID
    source_run_id: UUID
    source_turn_id: UUID
    knowledge_release_id: str
    phenomenon: str
    research_intent: str | None
    context: str | None
    version: int
    status: Literal["pending_confirmation", "confirmed"]
    requires_user_confirmation: bool
    confirmed_task_id: UUID | None
    created_at: datetime
    confirmed_at: datetime | None

    @classmethod
    def from_domain(
        cls, proposal: ResearchStartProposal
    ) -> "ResearchStartProposalResponse":
        return cls(
            proposal_id=proposal.proposal_id,
            conversation_id=proposal.conversation_id,
            source_run_id=proposal.source_run_id,
            source_turn_id=proposal.source_turn_id,
            knowledge_release_id=proposal.knowledge_release_id,
            phenomenon=proposal.phenomenon,
            research_intent=proposal.research_intent,
            context=proposal.context,
            version=proposal.version,
            status=proposal.status.value,
            requires_user_confirmation=proposal.confirmed_task_id is None,
            confirmed_task_id=proposal.confirmed_task_id,
            created_at=proposal.created_at,
            confirmed_at=proposal.confirmed_at,
        )


class ConfirmResearchStartRequest(BaseModel):
    expected_version: int = Field(ge=1)
    phenomenon: str = Field(min_length=1, max_length=10000)
    research_intent: str | None = Field(default=None, max_length=4000)
    context: str | None = Field(default=None, max_length=10000)


class ConfirmResearchStartResponse(BaseModel):
    conversation_id: UUID
    status: Literal["task_bound"]
    task_id: UUID
    proposal: ResearchStartProposalResponse
    navigation: ResearchTaskNavigationResponse


class AgentResearchJourneyResponse(BaseModel):
    conversation_id: UUID
    status: Literal["collecting", "proposal_pending", "task_bound"]
    task_id: UUID | None
    proposal: ResearchStartProposalResponse | None
    navigation: ResearchTaskNavigationResponse | None
