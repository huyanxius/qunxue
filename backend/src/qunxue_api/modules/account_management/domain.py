from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from qunxue_api.modules.identity import AccountRole, AccountStatus

SECONDARY_USE_POLICY_VERSION = "2026-08-secondary-use-v1"


@dataclass(frozen=True, slots=True)
class ModelSecondaryUseAuthorization:
    """A versioned snapshot for optional product-improvement use.

    Required inference for the user's active research is a separate processing
    purpose and is deliberately not represented by this opt-in.
    """

    user_id: UUID
    allowed: bool
    policy_version: str
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class AccountSummary:
    user_id: UUID
    email: str
    display_name: str | None
    role: AccountRole
    status: AccountStatus
    version: int
    created_at: datetime
    last_login_at: datetime | None

