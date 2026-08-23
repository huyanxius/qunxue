class ResearchTaskNotFound(Exception):
    code = "research_task_not_found"

    def __init__(self, task_id: str) -> None:
        super().__init__(f"Research task {task_id} was not found.")


class ResearchStartProposalNotFound(Exception):
    code = "research_start_proposal_not_found"

    def __init__(self, proposal_id: str) -> None:
        super().__init__(f"Research start proposal {proposal_id} was not found.")


class ResearchStartIdempotencyConflict(Exception):
    code = "research_start_idempotency_conflict"

    def __init__(self) -> None:
        super().__init__("Idempotency-Key was already used for another confirmation payload.")


class ResearchStartProposalConflict(Exception):
    code = "research_start_proposal_conflict"

    def __init__(
        self,
        message: str = "Research start proposal is stale or already changed.",
    ) -> None:
        super().__init__(message)


class ResearchStartSourceIncomplete(Exception):
    code = "research_start_source_incomplete"

    def __init__(self) -> None:
        super().__init__("Research start proposals require a completed Agent run and turn.")
