"""SQLite adapter registry used by migrations and the composition root."""

from qunxue_api.adapters.sqlite.account_management_model import (
    AccountAuditEventRow,
    AccountMutationRequestRow,
    AccountPasswordResetRow,
    AccountSystemStateRow,
    PersonalDataExportRow,
    UserPreferenceRow,
)
from qunxue_api.adapters.sqlite.agent_conversation_model import (
    AgentConversationRow,
    AgentMessageRow,
    AgentRunRow,
)
from qunxue_api.adapters.sqlite.base import Base
from qunxue_api.adapters.sqlite.identity_model import UserRow, UserSessionRow
from qunxue_api.adapters.sqlite.knowledge_catalog_model import (
    KnowledgeEntryReviewRow,
    KnowledgeEntryRevisionRow,
    KnowledgeRelationCandidateRow,
    KnowledgeRelationRow,
    KnowledgeReleaseRow,
    KnowledgeSourceRow,
    KnowledgeTheoryProfileRow,
)
from qunxue_api.adapters.sqlite.model_invocation_model import ModelInvocationRow
from qunxue_api.adapters.sqlite.research_document import SqliteResearchDocumentRepository
from qunxue_api.adapters.sqlite.research_document_model import (
    ResearchDocumentMutationRequestRow,
    ResearchDocumentVersionRow,
)
from qunxue_api.adapters.sqlite.research_document_mutation import (
    SqliteResearchDocumentMutationRepository,
)
from qunxue_api.adapters.sqlite.research_document_proposal import (
    SqliteResearchDocumentProposalRepository,
)
from qunxue_api.adapters.sqlite.research_document_proposal_model import (
    ResearchDocumentProposalRow,
)
from qunxue_api.adapters.sqlite.research_intake_model import (
    MaterialIntakeRunRow,
    PhenomenonCandidateVersionRow,
    PhenomenonExampleRow,
    PhenomenonStateRow,
    ResearchTaskRow,
)
from qunxue_api.adapters.sqlite.theory_matching_model import (
    ConfirmedTheoryPlanRow,
    MatchRunRow,
    TheoryDecisionSetRow,
    TheoryMatchingRequestRow,
)

__all__ = [
    "Base",
    "AccountAuditEventRow",
    "AccountMutationRequestRow",
    "AccountPasswordResetRow",
    "AccountSystemStateRow",
    "ConfirmedTheoryPlanRow",
    "AgentConversationRow",
    "AgentMessageRow",
    "AgentRunRow",
    "KnowledgeEntryReviewRow",
    "KnowledgeEntryRevisionRow",
    "KnowledgeRelationRow",
    "KnowledgeRelationCandidateRow",
    "KnowledgeReleaseRow",
    "KnowledgeSourceRow",
    "KnowledgeTheoryProfileRow",
    "ModelInvocationRow",
    "MaterialIntakeRunRow",
    "MatchRunRow",
    "PhenomenonCandidateVersionRow",
    "PhenomenonExampleRow",
    "PhenomenonStateRow",
    "PersonalDataExportRow",
    "ResearchTaskRow",
    "ResearchDocumentVersionRow",
    "ResearchDocumentMutationRequestRow",
    "SqliteResearchDocumentMutationRepository",
    "SqliteResearchDocumentRepository",
    "ResearchDocumentProposalRow",
    "SqliteResearchDocumentProposalRepository",
    "TheoryMatchingRequestRow",
    "TheoryDecisionSetRow",
    "UserRow",
    "UserPreferenceRow",
    "UserSessionRow",
]
