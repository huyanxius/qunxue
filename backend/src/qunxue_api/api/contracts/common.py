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
    RESEARCH_TASK_NOT_FOUND = "research_task_not_found"
    VALIDATION_ERROR = "validation_error"
    PHENOMENON_UNCONFIRMED = "phenomenon_unconfirmed"
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
