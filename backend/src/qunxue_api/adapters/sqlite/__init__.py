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
from qunxue_api.adapters.sqlite.billing_model import (
    CreditAccountRow,
    CreditLedgerRow,
    CreditRedemptionCodeRow,
)
from qunxue_api.adapters.sqlite.identity_model import (
    RegistrationVerificationRow,
    UserRow,
    UserSessionRow,
)
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
from qunxue_api.adapters.sqlite.professional_material_model import (
    LiteratureEntryRow,
    MaterialArchiveProfileRow,
    MaterialBatchRow,
    MaterialCollectionRow,
    MaterialRelationRow,
    ResearchCaseRow,
)
from qunxue_api.adapters.sqlite.professional_material_repository import (
    SqliteProfessionalMaterialRepository,
)
from qunxue_api.adapters.sqlite.research_analysis_model import (
    ResearchAnalysisWriteRequestRow,
    ResearchAnnotationRow,
    ResearchCodeRow,
    ResearchComparisonRow,
    ResearchMemoRow,
)
from qunxue_api.adapters.sqlite.research_analysis_repository import (
    SqliteResearchAnalysisRepository,
)
from qunxue_api.adapters.sqlite.research_cycle_model import ResearchCycleSnapshotRow
from qunxue_api.adapters.sqlite.research_cycle_repository import SqliteResearchCycleRepository
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
    ResearchStartConfirmationRow,
    ResearchStartProposalRow,
    ResearchTaskRow,
)
from qunxue_api.adapters.sqlite.research_material_model import (
    ResearchMaterialBlobRow,
    ResearchMaterialBlockRow,
    ResearchMaterialParseVersionRow,
    ResearchMaterialReparseRequestRow,
    ResearchMaterialRow,
)
from qunxue_api.adapters.sqlite.research_material_repository import (
    SqliteResearchMaterialRepository,
)
from qunxue_api.adapters.sqlite.research_project_audit import (
    SqliteResearchProjectAuditRepository,
)
from qunxue_api.adapters.sqlite.research_project_audit_model import (
    ResearchProjectAuditEventRow,
    ResearchProjectExchangeRunRow,
)
from qunxue_api.adapters.sqlite.research_method_model import (
    ResearchMethodPlanIdentityRow,
    ResearchMethodPlanVersionRow,
)
from qunxue_api.adapters.sqlite.research_method_repository import SqliteMethodPlanRepository
from qunxue_api.adapters.sqlite.research_start_proposal import (
    SqliteResearchStartProposalRepository,
)
from qunxue_api.adapters.sqlite.theory_matching_model import (
    ConfirmedTheoryPlanRow,
    MatchRunRow,
    TheoryDecisionDraftRequestRow,
    TheoryDecisionDraftRow,
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
    "CreditAccountRow",
    "CreditLedgerRow",
    "CreditRedemptionCodeRow",
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
    "LiteratureEntryRow",
    "MaterialArchiveProfileRow",
    "MaterialBatchRow",
    "MaterialCollectionRow",
    "MaterialRelationRow",
    "ResearchCaseRow",
    "SqliteProfessionalMaterialRepository",
    "MaterialIntakeRunRow",
    "MatchRunRow",
    "PhenomenonCandidateVersionRow",
    "PhenomenonExampleRow",
    "PhenomenonStateRow",
    "PersonalDataExportRow",
    "ResearchTaskRow",
    "ResearchMaterialRow",
    "ResearchMaterialBlobRow",
    "ResearchMaterialParseVersionRow",
    "ResearchMaterialReparseRequestRow",
    "ResearchMaterialBlockRow",
    "SqliteResearchMaterialRepository",
    "ResearchProjectAuditEventRow",
    "ResearchProjectExchangeRunRow",
    "SqliteResearchProjectAuditRepository",
    "ResearchAnnotationRow",
    "ResearchAnalysisWriteRequestRow",
    "ResearchCodeRow",
    "ResearchComparisonRow",
    "ResearchMemoRow",
    "SqliteResearchAnalysisRepository",
    "ResearchMethodPlanIdentityRow",
    "ResearchMethodPlanVersionRow",
    "ResearchCycleSnapshotRow",
    "SqliteMethodPlanRepository",
    "SqliteResearchCycleRepository",
    "ResearchDocumentVersionRow",
    "ResearchDocumentMutationRequestRow",
    "SqliteResearchDocumentMutationRepository",
    "SqliteResearchDocumentRepository",
    "ResearchDocumentProposalRow",
    "ResearchStartConfirmationRow",
    "ResearchStartProposalRow",
    "RegistrationVerificationRow",
    "SqliteResearchStartProposalRepository",
    "SqliteResearchDocumentProposalRepository",
    "TheoryMatchingRequestRow",
    "TheoryDecisionDraftRow",
    "TheoryDecisionDraftRequestRow",
    "TheoryDecisionSetRow",
    "UserRow",
    "UserPreferenceRow",
    "UserSessionRow",
]
