class ResearchFrameworkError(ValueError):
    pass


class FrameworkNotFound(ResearchFrameworkError):
    pass


class FrameworkRevisionConflict(ResearchFrameworkError):
    pass


class FrameworkAuditConflict(ResearchFrameworkError):
    pass


class FrameworkConfirmationBlocked(ResearchFrameworkError):
    def __init__(self, finding_ids: tuple[object, ...]) -> None:
        self.finding_ids = finding_ids
        super().__init__("unresolved blocking audit findings prevent confirmation")
