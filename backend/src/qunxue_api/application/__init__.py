"""Cross-module use-case composition. Business rules remain inside their owners."""

from qunxue_api.application.disciplinary_agent import (
    AgentTurnExecution,
    DisciplinaryAgentApplication,
)
from qunxue_api.application.research_analysis import ResearchAnalysisApplication
from qunxue_api.application.research_document_proposals import (
    ResearchDocumentProposalApplication,
)
from qunxue_api.application.research_documents import ResearchDocumentApplication
from qunxue_api.application.research_journey import (
    ResearchJourney,
    ResearchJourneyConfigurationError,
    ResearchJourneyDependencies,
)
from qunxue_api.application.research_materials import ResearchMaterialApplication
from qunxue_api.application.research_method import ResearchMethodPlanApplication
from qunxue_api.application.research_start import (
    ResearchStartApplication,
    ResearchStartConfirmationResult,
    ResearchStartJourneyState,
)
from qunxue_api.application.theory_matching import (
    MatchingCatalogNotReady,
    MatchingRequestConflict,
    MatchingSnapshotConflict,
    TheoryMatchingApplication,
)

__all__ = [
    "ResearchJourney",
    "ResearchDocumentApplication",
    "ResearchDocumentProposalApplication",
    "ResearchAnalysisApplication",
    "ResearchJourneyConfigurationError",
    "ResearchJourneyDependencies",
    "ResearchMaterialApplication",
    "ResearchMethodPlanApplication",
    "ResearchStartApplication",
    "ResearchStartConfirmationResult",
    "ResearchStartJourneyState",
    "MatchingRequestConflict",
    "MatchingCatalogNotReady",
    "MatchingSnapshotConflict",
    "TheoryMatchingApplication",
    "AgentTurnExecution",
    "DisciplinaryAgentApplication",
]
