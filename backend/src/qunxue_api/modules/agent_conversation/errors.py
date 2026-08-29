class AgentConversationError(RuntimeError):
    """Base error for the independent Agent conversation boundary."""


class ConversationNotFound(AgentConversationError, LookupError):
    pass


class ConversationTaskBindingConflict(AgentConversationError):
    """A turn attempted to use a task other than the conversation's bound task."""

    code = "research_task_binding_conflict"


class ResearchMaterialCitationUnavailable(AgentConversationError):
    """A personal source stopped being eligible before the turn was saved."""

    code = "research_material_citation_unavailable"


class RunAlreadyActive(AgentConversationError):
    pass


class AgentInterrupted(AgentConversationError):
    """The client stopped a run before an assistant turn was persisted."""
