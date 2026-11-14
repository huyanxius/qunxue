"""One safe JSON/SSE boundary for billing failures; never expose provider bodies."""

import logging
from uuid import uuid4

from fastapi.responses import JSONResponse

from qunxue_api.api.contracts.common import ErrorCode, ErrorDetail, ErrorResponse
from qunxue_api.modules.billing import (
    BillingBudgetExceeded,
    BillingFailure,
    BillingReplayBlocked,
    CreditRunInProgress,
    CreditsDepleted,
    is_credit_shortage,
)

logger = logging.getLogger(__name__)

AGENT_FAILURE_MESSAGE = "本轮未完成。你的问题还在，可以重新发送。"


def billing_error(error):
    if is_credit_shortage(error):
        return 402, ErrorCode.CREDITS_DEPLETED, "额度不足，请前往账户设置查看积分。"
    if isinstance(error, CreditRunInProgress) or (
        isinstance(error, BillingBudgetExceeded) and error.reason == "credits_frozen"
    ):
        return 409, ErrorCode.CREDIT_RUN_IN_PROGRESS, "已有一轮在进行，完成后可继续发送。"
    if isinstance(error, BillingReplayBlocked):
        return 409, ErrorCode.CONFLICT, "这条请求已处理，请刷新查看结果。"
    logger.warning("Billing operation stopped: %s (%s)", type(error).__name__, error.reason)
    return 503, ErrorCode.CAPABILITY_UNAVAILABLE, AGENT_FAILURE_MESSAGE


def install_billing_error_handlers(app):
    async def handle(_request, error):
        status, code, message = billing_error(error)
        body = ErrorResponse(error=ErrorDetail(code=code, message=message, trace_id=str(uuid4())))
        return JSONResponse(status_code=status, content=body.model_dump(mode="json"))

    for error_type in (BillingFailure, CreditRunInProgress, CreditsDepleted):
        app.add_exception_handler(error_type, handle)
