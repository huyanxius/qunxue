from dataclasses import dataclass
from datetime import datetime
from math import ceil
from typing import Literal
from uuid import UUID

WELCOME_GRANT = 10_000
INPUT_TOKENS_PER_CREDIT = 100
OUTPUT_TOKENS_PER_CREDIT = 25


class CreditsDepleted(Exception):
    code = "credits_depleted"

    def __init__(self) -> None:
        super().__init__("积分不足，请在账户设置中查看用量。")


class CreditRunInProgress(Exception):
    code = "credit_run_in_progress"

    def __init__(self) -> None:
        super().__init__("当前账户已有一轮对话正在计费。")


class CreditCodeUnavailable(Exception):
    code = "credit_code_unavailable"

    def __init__(self) -> None:
        super().__init__("兑换码无效、已过期或已被其他账户使用。")


class CreditCodeBatchConflict(Exception):
    code = "credit_code_batch_conflict"

    def __init__(self) -> None:
        super().__init__("同一批次请求不能修改积分、数量或有效期。")


@dataclass(frozen=True, slots=True)
class CreditEntry:
    entry_id: UUID
    kind: Literal["signup_grant", "usage", "redemption"]
    points: int
    balance_after: int
    input_tokens: int
    output_tokens: int
    model: str | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class CreditSummary:
    balance: int
    entries: tuple[CreditEntry, ...]
    total_entries: int
    next_cursor: str | None
    is_unlimited: bool = False


@dataclass(frozen=True, slots=True)
class CreditCodeSpec:
    code_id: UUID
    batch_id: str
    code_index: int
    code_hash: str
    created_by_user_id: UUID
    created_at: datetime
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class GeneratedCreditCodeBatch:
    codes: tuple[str, ...]
    points: int
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class CreditRedemption:
    redeemed_points: int
    balance: int


def usage_credit_cost(*, input_tokens: int, output_tokens: int) -> int:
    if input_tokens < 0 or output_tokens < 0:
        raise ValueError("token usage must not be negative")
    if input_tokens == 0 and output_tokens == 0:
        return 0
    return max(
        1,
        ceil(input_tokens / INPUT_TOKENS_PER_CREDIT)
        + ceil(output_tokens / OUTPUT_TOKENS_PER_CREDIT),
    )
