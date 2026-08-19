class AgentConversationError(RuntimeError):
    """Base error for the independent Agent conversation boundary."""


class ConversationNotFound(AgentConversationError, LookupError):
    pass


class RunAlreadyActive(AgentConversationError):
    pass


class AgentInterrupted(AgentConversationError):
    """The client stopped a run before an assistant turn was persisted."""
