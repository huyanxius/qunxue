from typing import Literal

from pydantic import BaseModel

from qunxue_api.api.contracts.common import ModelCapability


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    runtime_mode: Literal["inline_demo"]
    persistence: Literal["sqlite"]
    contract_version: str
    capability: Literal["unavailable"] | ModelCapability
    knowledge_release_id: str | None
