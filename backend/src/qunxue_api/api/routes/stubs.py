from typing import Annotated
from uuid import uuid4

from fastapi import Header, status
from fastapi.responses import JSONResponse

from qunxue_api.api.contracts.common import ErrorDetail, ErrorResponse

IdempotencyKey = Annotated[
    str,
    Header(alias="Idempotency-Key", min_length=8, max_length=128),
]


def not_implemented_response() -> JSONResponse:
    body = ErrorResponse(
        error=ErrorDetail(
            code="not_implemented",
            message="This contract is frozen but not implemented.",
            trace_id=str(uuid4()),
        )
    )
    return JSONResponse(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        content=body.model_dump(mode="json"),
    )
