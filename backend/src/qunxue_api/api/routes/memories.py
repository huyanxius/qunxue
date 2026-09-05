from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from qunxue_api.api.dependencies import CurrentSessionDependency
from qunxue_api.api.routes.stubs import IdempotencyKey
from qunxue_api.modules.agent_memory import MemoryConflict, MemoryNotFound, MemoryService

router = APIRouter(prefix="/api/memories", tags=["memory"])


class MemoryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_id: UUID | None = None
    key: str = Field(min_length=1, max_length=64)
    content: str = Field(min_length=1, max_length=2000)


class MemoryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(min_length=1, max_length=2000)
    expected_version: int = Field(ge=1)


class MemoryResponse(BaseModel):
    memory_id: UUID
    task_id: UUID | None
    key: str
    content: str
    origin: Literal["manual", "explicit", "learned"]
    version: int
    created_at: datetime
    updated_at: datetime
    source_conversation_id: UUID | None
    source_message_id: UUID | None
    source_quote: str | None


class MemoryList(BaseModel):
    items: list[MemoryResponse]


class MemorySettings(BaseModel):
    task_id: UUID | None
    version: int
    use_memory: bool
    learn_memory: bool


class MemorySettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=0)
    use_memory: bool
    learn_memory: bool


@contextmanager
def service(request: Request) -> Iterator[MemoryService]:
    try:
        with request.app.state.memory_service_scope() as memory:
            yield memory
    except MemoryNotFound as error:
        raise HTTPException(404, str(error)) from error
    except MemoryConflict as error:
        raise HTTPException(409, str(error)) from error
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@router.get("", response_model=MemoryList, operation_id="list_memories")
def list_memories(request: Request, current: CurrentSessionDependency, task_id: UUID | None = None):
    with service(request) as memory:
        return MemoryList(
            items=[
                MemoryResponse(**asdict(m))
                for m in memory.repository.list(current.user.user_id, task_id)
            ]
        )


@router.post("", response_model=MemoryResponse, status_code=201, operation_id="create_memory")
def create_memory(
    payload: MemoryCreate,
    request: Request,
    current: CurrentSessionDependency,
    idempotency_key: IdempotencyKey,
):
    with service(request) as memory:
        return MemoryResponse(
            **asdict(
                memory.save(
                    user_id=current.user.user_id,
                    **payload.model_dump(),
                    origin="manual",
                    idempotency_key=idempotency_key,
                )
            )
        )


@router.get("/settings", response_model=MemorySettings, operation_id="get_memory_settings")
def get_settings(request: Request, current: CurrentSessionDependency, task_id: UUID | None = None):
    with service(request) as memory:
        return MemorySettings(**asdict(memory.repository.scope(current.user.user_id, task_id)))


@router.patch("/settings", response_model=MemorySettings, operation_id="update_memory_settings")
def update_settings(
    payload: MemorySettingsUpdate,
    request: Request,
    current: CurrentSessionDependency,
    _idempotency_key: IdempotencyKey,
    task_id: UUID | None = None,
):
    with service(request) as memory:
        return MemorySettings(
            **asdict(
                memory.repository.configure(
                    current.user.user_id,
                    task_id,
                    **payload.model_dump(),
                )
            )
        )


@router.get("/{memory_id}", response_model=MemoryResponse, operation_id="get_memory")
def get_memory(memory_id: UUID, request: Request, current: CurrentSessionDependency):
    with service(request) as memory:
        return MemoryResponse(**asdict(memory.repository.get(current.user.user_id, memory_id)))


@router.patch("/{memory_id}", response_model=MemoryResponse, operation_id="update_memory")
def update_memory(
    memory_id: UUID,
    payload: MemoryUpdate,
    request: Request,
    current: CurrentSessionDependency,
    idempotency_key: IdempotencyKey,
):
    with service(request) as memory:
        existing = memory.repository.get(current.user.user_id, memory_id)
        return MemoryResponse(
            **asdict(
                memory.save(
                    user_id=current.user.user_id,
                    task_id=existing.task_id,
                    key=existing.key,
                    memory_id=memory_id,
                    **payload.model_dump(),
                    origin="manual",
                    idempotency_key=idempotency_key,
                )
            )
        )


@router.delete("/{memory_id}", status_code=204, operation_id="delete_memory")
def delete_memory(
    memory_id: UUID,
    request: Request,
    current: CurrentSessionDependency,
    _idempotency_key: IdempotencyKey,
    expected_version: int = Query(ge=1),
):
    with service(request) as memory:
        memory.repository.delete(current.user.user_id, memory_id, expected_version)
    return Response(status_code=204)


@router.get(
    "/{memory_id}/revisions", response_model=MemoryList, operation_id="list_memory_revisions"
)
def list_revisions(memory_id: UUID, request: Request, current: CurrentSessionDependency):
    with service(request) as memory:
        return MemoryList(
            items=[
                MemoryResponse(**asdict(m))
                for m in memory.repository.revisions(current.user.user_id, memory_id)
            ]
        )
