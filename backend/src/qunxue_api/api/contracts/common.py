from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel


class ErrorCode(StrEnum):
    UNAUTHENTICATED = "unauthenticated"
    SESSION_EXPIRED = "session_expired"
    FORBIDDEN = "forbidden"
    NOT_FOUND = "not_found"
    METHOD_NOT_ALLOWED = "method_not_allowed"
    CONFLICT = "conflict"
    IDEMPOTENCY_CONFLICT = "idempotency_conflict"
    REAUTHENTICATION_REQUIRED = "reauthentication_required"
    ACCOUNT_INACTIVE = "account_inactive"
    CAPABILITY_UNAVAILABLE = "capability_unavailable"
    PROVISIONED_ADMINISTRATOR_PROTECTED = "provisioned_administrator_protected"
    PASSWORD_RESET_INVALID = "password_reset_invalid"
    TOKEN_EXPIRED = "token_expired"
    CREDIT_CODE_UNAVAILABLE = "credit_code_unavailable"
    CREDIT_CODE_BATCH_CONFLICT = "credit_code_batch_conflict"
    EMAIL_VERIFICATION_INVALID = "email_verification_invalid"
    EMAIL_VERIFICATION_RATE_LIMITED = "email_verification_rate_limited"
    EMAIL_DELIVERY_UNAVAILABLE = "email_delivery_unavailable"
    RESEARCH_TASK_NOT_FOUND = "research_task_not_found"
    RESEARCH_START_PROPOSAL_NOT_FOUND = "research_start_proposal_not_found"
    RESEARCH_START_IDEMPOTENCY_CONFLICT = "research_start_idempotency_conflict"
    RESEARCH_START_PROPOSAL_CONFLICT = "research_start_proposal_conflict"
    RESEARCH_START_SOURCE_INCOMPLETE = "research_start_source_incomplete"
    RESEARCH_MATERIAL_NOT_FOUND = "research_material_not_found"
    RESEARCH_MATERIAL_TOO_LARGE = "research_material_too_large"
    UNSUPPORTED_MATERIAL_FORMAT = "unsupported_material_format"
    NO_EXTRACTABLE_TEXT = "no_extractable_text"
    RESEARCH_MATERIAL_IDEMPOTENCY_CONFLICT = "research_material_idempotency_conflict"
    RESEARCH_MATERIAL_VERSION_CONFLICT = "research_material_version_conflict"
    VALIDATION_ERROR = "validation_error"
    PHENOMENON_UNCONFIRMED = "phenomenon_unconfirmed"
    CATALOG_NOT_READY = "catalog_not_ready"
    RETRIEVAL_UNAVAILABLE = "retrieval_unavailable"
    NO_ADOPTED_THEORY = "no_adopted_theory"
    CANDIDATE_INELIGIBLE = "candidate_ineligible"
    EXTERNAL_CANDIDATE_ADOPTION_BLOCKED = "external_candidate_adoption_blocked"
    MODEL_TIMEOUT = "model_timeout"
    NO_RELIABLE_CANDIDATE = "no_reliable_candidate"
    INSUFFICIENT_SOURCES = "insufficient_sources"
    STALE_FRAMEWORK_REVISION = "stale_framework_revision"
    UNRESOLVED_BLOCKING_AUDIT = "unresolved_blocking_audit"
    NOT_IMPLEMENTED = "not_implemented"
    INTERNAL_SERVER_ERROR = "internal_server_error"


class ModelCapability(StrEnum):
    MOCK = "mock"
    BASE = "base"
    SFT = "sft"


class TraceMetadata(BaseModel):
    trace_id: UUID
    request_id: UUID
    contract_version: str


class ModelMetadata(BaseModel):
    provider: str
    model_version: str
    capability: ModelCapability
    degraded: bool
    knowledge_release_id: str | None
    trace: TraceMetadata


class ErrorDetail(BaseModel):
    code: ErrorCode
    message: str
    trace_id: str


class ErrorResponse(BaseModel):
    error: ErrorDetail
