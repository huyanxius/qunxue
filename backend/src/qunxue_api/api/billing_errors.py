"""One safe JSON/SSE boundary for billing failures; never expose provider bodies."""

from uuid import uuid4

from fastapi.responses import JSONResponse

from qunxue_api.api.contracts.common import ErrorCode, ErrorDetail, ErrorResponse
from qunxue_api.modules.billing import (
    BillingBudgetExceeded,
    BillingContextMissing,
    BillingFailure,
    BillingReplayBlocked,
    CreditRunInProgress,
    CreditsDepleted,
    UnknownPrice,
)


def billing_error(error):
    if isinstance(error, CreditsDepleted) or (
        isinstance(error, BillingBudgetExceeded) and error.reason == "credits_depleted"
    ):
        return 402, ErrorCode.CREDITS_DEPLETED, "积分不足，请前往账户设置查看用量。"
    if isinstance(error, CreditRunInProgress) or (
        isinstance(error, BillingBudgetExceeded) and error.reason == "credits_frozen"
    ):
        return 409, ErrorCode.CREDIT_RUN_IN_PROGRESS, "当前账户有积分正在冻结，请稍后重试。"
    if isinstance(error, BillingReplayBlocked):
        return (
            409,
            ErrorCode.BILLING_REPLAY_BLOCKED,
            "本轮请求已处理，请刷新查看结果；不会重复扣费。",
        )
    if isinstance(error, (BillingContextMissing, UnknownPrice)):
        return 503, ErrorCode.BILLING_NOT_CONFIGURED, "计费配置暂未启用，本轮未扣费，请稍后重试。"
    if isinstance(error, BillingBudgetExceeded):
        return (
            429,
            ErrorCode.BILLING_BUDGET_EXCEEDED,
            "本轮请求超过费用上限，已停止且未扣费，请稍后重试。",
        )
    return 502, ErrorCode.BILLING_PROVIDER_ERROR, "模型费用或输出尚未确认，本轮未扣费，请稍后重试。"


def install_billing_error_handlers(app):
    async def handle(_request, error):
        status, code, message = billing_error(error)
        body = ErrorResponse(error=ErrorDetail(code=code, message=message, trace_id=str(uuid4())))
        return JSONResponse(status_code=status, content=body.model_dump(mode="json"))

    for error_type in (BillingFailure, CreditRunInProgress, CreditsDepleted):
        app.add_exception_handler(error_type, handle)
