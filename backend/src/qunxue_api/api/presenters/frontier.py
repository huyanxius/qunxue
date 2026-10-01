"""Declared public DTO fields only; source material remains in internal storage."""

from copy import deepcopy

from qunxue_api.api.contracts.frontier import FrontierEvidenceResponse, FrontierRecordResponse


def public_record(value: dict) -> dict:
    result = {
        key: deepcopy(value[key]) for key in FrontierRecordResponse.model_fields if key in value
    }
    result["evidence"] = [
        {key: deepcopy(item[key]) for key in FrontierEvidenceResponse.model_fields if key in item}
        for item in value.get("evidence", [])
    ]
    return result
