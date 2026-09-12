"""Private, account-scoped editing of deployed rehearsal cases."""

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, model_validator

from qunxue_api.api.dependencies import CurrentSessionDependency

router = APIRouter(prefix="/api/roadshow", tags=["roadshow"])
CONFIG_PATH = Path(__file__).resolve().parents[4] / "var" / "roadshow.json"


class RoadshowCase(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    keywords: list[str] = Field(min_length=1, max_length=20)
    question: str = Field(min_length=1, max_length=4000)
    options: list[str] = Field(min_length=1, max_length=8)
    steps: list[str] = Field(min_length=1, max_length=12)
    knowledge_queries: list[str] = Field(default_factory=list, max_length=5)
    web_queries: list[str] = Field(default_factory=list, max_length=5)
    answer: str = Field(min_length=1, max_length=200000)

    @model_validator(mode="after")
    def valid_keywords(self):
        if any(not word.strip() for word in self.keywords):
            raise ValueError("触发词不能为空")
        return self


class RoadshowSettings(BaseModel):
    enabled: bool = True
    canvas_enabled: bool = True
    active_case: int = Field(default=0, ge=0)
    chunk_delay: float = Field(default=0.025, ge=0, le=0.5)
    cases: list[RoadshowCase] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def valid_selection(self):
        if self.active_case >= len(self.cases):
            raise ValueError("所选案例不存在")
        return self


def _config(request, current):
    path = getattr(request.app.state, "roadshow_path", CONFIG_PATH)
    if not path.is_file():
        raise HTTPException(404, "Not found")
    data = json.loads(path.read_text())
    if data.get("user_id") != str(current.user.user_id):
        raise HTTPException(404, "Not found")
    return path, data


def _write(path, data):
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    temporary.chmod(0o600)
    temporary.replace(path)


@router.get("", response_model=RoadshowSettings, operation_id="get_roadshow_settings")
def get_settings(request: Request, current: CurrentSessionDependency):
    path, data = _config(request, current)
    original = path.with_name("roadshow.original.json")
    if not original.exists():
        _write(original, data)
    return RoadshowSettings.model_validate(data)


@router.put("", response_model=RoadshowSettings, operation_id="save_roadshow_settings")
def save_settings(payload: RoadshowSettings, request: Request, current: CurrentSessionDependency):
    path, data = _config(request, current)
    original = path.with_name("roadshow.original.json")
    if not original.exists():
        _write(original, data)
    _write(path, {"user_id": data["user_id"], **payload.model_dump()})
    return payload


@router.post("/reset", response_model=RoadshowSettings, operation_id="reset_roadshow_settings")
def reset_settings(request: Request, current: CurrentSessionDependency):
    path, data = _config(request, current)
    original = path.with_name("roadshow.original.json")
    if original.exists():
        data = json.loads(original.read_text())
        _write(path, data)
    return RoadshowSettings.model_validate(data)
