"""Errors raised by the long-lived research-material boundary."""


class ResearchMaterialError(Exception):
    """Base error for material validation and lifecycle failures."""

    code = "research_material_error"


class UnsupportedMaterialFormat(ResearchMaterialError, ValueError):
    code = "unsupported_material_format"

    def __init__(self, media_type: str | None = None) -> None:
        self.media_type = media_type
        detail = media_type or "unknown"
        super().__init__(f"unsupported research material format: {detail}")


class MaterialNotFound(ResearchMaterialError):
    code = "research_material_not_found"


class MaterialDeleted(ResearchMaterialError):
    code = "research_material_deleted"


class MaterialOwnershipError(ResearchMaterialError):
    code = "research_material_not_owned"


class MaterialIdempotencyConflict(ResearchMaterialError):
    code = "research_material_idempotency_conflict"


class MaterialVersionConflict(ResearchMaterialError):
    code = "research_material_version_conflict"


class MaterialParseError(ResearchMaterialError):
    """Stable parse failure shared by adapters and application/API layers."""

    code = "research_material_parse_error"

    def __init__(self, code: str | None = None, message: str | None = None) -> None:
        if code:
            self.code = code
        detail = message or self.code
        super().__init__(f"{self.code}: {detail}")


class DoiMetadataUnavailable(ResearchMaterialError):
    """The external DOI registry could not provide a usable response."""

    code = "doi_metadata_unavailable"
