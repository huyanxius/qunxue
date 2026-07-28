class ResearchTaskNotFound(Exception):
    code = "research_task_not_found"

    def __init__(self, task_id: str) -> None:
        super().__init__(f"Research task {task_id} was not found.")
