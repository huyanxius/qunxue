class ResearchTaskNotFound(Exception):
    code = 'research_task_not_found'

    def __init__(self, task_id: str) -> None:
        super().__init__(f"研究任务 '{task_id}' 不存在。")


class ResearchIntakeValidationError(ValueError):
    code = 'invalid_research_intake'

    def __init__(self, message: str) -> None:
        super().__init__(message)