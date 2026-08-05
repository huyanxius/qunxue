class ResearchTaskNotFound(Exception):
    code = "research_task_not_found"

    def __init__(self, task_id: str) -> None:
        super().__init__(f"research task '{task_id}' was not found")


class ResearchIntakeValidationError(ValueError):
    code = "invalid_research_intake"

    def __init__(self, message: str) -> None:
        super().__init__(message)
