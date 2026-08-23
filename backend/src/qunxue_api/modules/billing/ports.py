from datetime import datetime
from typing import Protocol
from uuid import UUID

from qunxue_api.modules.billing.domain import (
    CreditCodeSpec,
    CreditEntry,
    CreditRedemption,
    CreditSummary,
)


class CreditRepository(Protocol):
    def ensure_welcome_grant(
        self,
        *,
        user_id: UUID,
        points: int,
        now: datetime,
    ) -> CreditSummary: ...

    def get_summary(
        self,
        *,
        user_id: UUID,
        limit: int,
        offset: int = 0,
    ) -> CreditSummary | None: ...

    def create_redemption_codes(self, *, codes: tuple[CreditCodeSpec, ...]) -> None: ...

    def redeem_code(
        self,
        *,
        user_id: UUID,
        code_hash: str,
        now: datetime,
    ) -> CreditRedemption: ...

    def reserve_usage(self, *, user_id: UUID, run_id: UUID, now: datetime) -> None: ...

    def release_usage(self, *, user_id: UUID, run_id: UUID, now: datetime) -> None: ...

    def charge_usage(
        self,
        *,
        user_id: UUID,
        run_id: UUID,
        points: int,
        input_tokens: int,
        output_tokens: int,
        model: str,
        now: datetime,
    ) -> CreditEntry: ...
