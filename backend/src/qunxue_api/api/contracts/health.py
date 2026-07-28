from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    runtime_mode: Literal["inline_demo"]
    persistence: Literal["sqlite"]
    contract_version: str
