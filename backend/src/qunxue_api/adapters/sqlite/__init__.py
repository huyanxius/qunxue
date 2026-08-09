"""SQLite adapter registry used by migrations and the composition root."""

from qunxue_api.adapters.sqlite.base import Base
from qunxue_api.adapters.sqlite.identity_model import UserRow, UserSessionRow
from qunxue_api.adapters.sqlite.knowledge_catalog_model import (
    KnowledgeEntryReviewRow,
    KnowledgeEntryRevisionRow,
    KnowledgeRelationRow,
    KnowledgeReleaseRow,
    KnowledgeSourceRow,
    KnowledgeTheoryProfileRow,
)
from qunxue_api.adapters.sqlite.model_invocation_model import ModelInvocationRow
from qunxue_api.adapters.sqlite.research_intake_model import (
    MaterialIntakeRunRow,
    PhenomenonCandidateVersionRow,
    PhenomenonExampleRow,
    PhenomenonStateRow,
    ResearchTaskRow,
)

__all__ = [
    "Base",
    "KnowledgeEntryReviewRow",
    "KnowledgeEntryRevisionRow",
    "KnowledgeRelationRow",
    "KnowledgeReleaseRow",
    "KnowledgeSourceRow",
    "KnowledgeTheoryProfileRow",
    "ModelInvocationRow",
    "MaterialIntakeRunRow",
    "PhenomenonCandidateVersionRow",
    "PhenomenonExampleRow",
    "PhenomenonStateRow",
    "ResearchTaskRow",
    "UserRow",
    "UserSessionRow",
]
