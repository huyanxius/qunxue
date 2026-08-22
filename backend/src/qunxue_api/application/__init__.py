"""Cross-module use-case composition. Business rules remain inside their owners."""

from qunxue_api.application.disciplinary_agent import (
    AgentTurnExecution,
    DisciplinaryAgentApplication,
)
from qunxue_api.application.research_document_proposals import (
    ResearchDocumentProposalApplication,
)
from qunxue_api.application.research_documents import ResearchDocumentApplication
from qunxue_api.application.research_journey import (
    ResearchJourney,
    ResearchJourneyConfigurationError,
    ResearchJourneyDependencies,
)
from qunxue_api.application.research_start import (
    ResearchStartApplication,
    ResearchStartConfirmationResult,
    ResearchStartJourneyState,
)
from qunxue_api.application.theory_matching import (
    MatchingRequestConflict,
    MatchingSnapshotConflict,
    TheoryMatchingApplication,
)

__all__ = [
    "ResearchJourney",
    "ResearchDocumentApplication",
    "ResearchDocumentProposalApplication",
    "ResearchJourneyConfigurationError",
    "ResearchJourneyDependencies",
    "ResearchStartApplication",
    "ResearchStartConfirmationResult",
    "ResearchStartJourneyState",
    "MatchingRequestConflict",
    "MatchingSnapshotConflict",
    "TheoryMatchingApplication",
    "AgentTurnExecution",
    "DisciplinaryAgentApplication",
]
