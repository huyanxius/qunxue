"""Public material domain boundary."""

from qunxue_api.modules.research_materials.domain import (
    MaterialBlock,
    MaterialFormat,
    MaterialKind,
    MaterialLocator,
    MaterialParseVersion,
    MaterialReparseRequest,
    MaterialStatus,
    ParsedMaterial,
    ResearchMaterial,
)
from qunxue_api.modules.research_materials.errors import (
    MaterialDeleted,
    MaterialIdempotencyConflict,
    MaterialNotFound,
    MaterialOwnershipError,
    MaterialParseError,
    MaterialVersionConflict,
    ResearchMaterialError,
    UnsupportedMaterialFormat,
)
from qunxue_api.modules.research_materials.ports import ResearchMaterialRepository
from qunxue_api.modules.research_materials.service import ResearchMaterialService

__all__ = [
    "MaterialBlock",
    "MaterialDeleted",
    "MaterialFormat",
    "MaterialIdempotencyConflict",
    "MaterialKind",
    "MaterialLocator",
    "MaterialNotFound",
    "MaterialOwnershipError",
    "MaterialParseError",
    "MaterialParseVersion",
    "MaterialReparseRequest",
    "MaterialStatus",
    "ParsedMaterial",
    "MaterialVersionConflict",
    "ResearchMaterial",
    "ResearchMaterialError",
    "ResearchMaterialRepository",
    "ResearchMaterialService",
    "UnsupportedMaterialFormat",
]
