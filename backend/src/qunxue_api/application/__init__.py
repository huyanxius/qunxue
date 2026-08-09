"""Cross-module use-case composition. Business rules remain inside their owners."""

from qunxue_api.application.research_journey import (
    ResearchJourney,
    ResearchJourneyConfigurationError,
    ResearchJourneyDependencies,
)
from qunxue_api.application.theory_matching import (
    MatchingRequestConflict,
    MatchingSnapshotConflict,
    TheoryMatchingApplication,
)

__all__ = [
    "ResearchJourney",
    "ResearchJourneyConfigurationError",
    "ResearchJourneyDependencies",
    "MatchingRequestConflict",
    "MatchingSnapshotConflict",
    "TheoryMatchingApplication",
]
