"""Knowledge-first conversational Agent domain and application service."""

from qunxue_api.modules.agent_conversation.domain import (
    AgentCitation,
    AgentMaterialAttachment,
    AgentMessage,
    AgentRun,
    AgentTurn,
    Conversation,
    IdempotentTurn,
    UserConversation,
)
from qunxue_api.modules.agent_conversation.errors import (
    AgentConversationError,
    AgentInterrupted,
    ConversationNotFound,
    ConversationTaskBindingConflict,
    ResearchMaterialCitationUnavailable,
    RunAlreadyActive,
)
from qunxue_api.modules.agent_conversation.ports import (
    AgentEvidence,
    AgentRelease,
    AgentResearchEvent,
    AgentRunResult,
    AgentRuntimeIdentity,
    AgentToolContext,
    AgentToolEvent,
    SubjectAgentRunner,
)
from qunxue_api.modules.agent_conversation.research_map import (
    aggregate_research_map,
    apply_research_map_patch,
    empty_research_map,
    normalize_research_map_patch,
    patches_from_tool_summary,
)
from qunxue_api.modules.agent_conversation.service import ConversationService

from .canvas_editing import CanvasEditConflict, apply_canvas_edits, prepare_canvas_edit

__all__ = [
    "CanvasEditConflict",
    "apply_canvas_edits",
    "prepare_canvas_edit",
    "AgentCitation",
    "AgentMaterialAttachment",
    "AgentEvidence",
    "AgentRelease",
    "AgentRuntimeIdentity",
    "AgentRunResult",
    "AgentResearchEvent",
    "AgentToolContext",
    "AgentToolEvent",
    "AgentConversationError",
    "AgentInterrupted",
    "ConversationTaskBindingConflict",
    "AgentMessage",
    "AgentRun",
    "AgentTurn",
    "Conversation",
    "ConversationNotFound",
    "ConversationService",
    "IdempotentTurn",
    "ResearchMaterialCitationUnavailable",
    "RunAlreadyActive",
    "UserConversation",
    "SubjectAgentRunner",
    "aggregate_research_map",
    "apply_research_map_patch",
    "empty_research_map",
    "normalize_research_map_patch",
    "patches_from_tool_summary",
]
