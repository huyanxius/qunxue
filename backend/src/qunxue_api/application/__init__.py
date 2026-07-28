"""Cross-module use-case composition. Business rules remain inside their owners."""

from qunxue_api.application.research_journey import (
    ResearchJourney,
    ResearchJourneyConfigurationError,
    ResearchJourneyDependencies,
)

__all__ = [
    "ResearchJourney",
    "ResearchJourneyConfigurationError",
    "ResearchJourneyDependencies",
]
