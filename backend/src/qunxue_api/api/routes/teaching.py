from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Request

from qunxue_api.api.contracts.teaching import (
    CreateTeachingActivity,
    LearningSummary,
    TeachingActivity,
    TeachingActivityList,
    TeachingSettings,
    TeachingSource,
    TeachingVersion,
    UpdateTeachingActivity,
    UpdateTeachingSettings,
)
from qunxue_api.api.dependencies import CurrentSessionDependency
from qunxue_api.api.routes.stubs import IdempotencyKey
from qunxue_api.application.teaching_assistant import TeachingAssistantApplication

router = APIRouter(prefix="/api", tags=["teaching-assistant"])


def get_application(request: Request):
    with request.app.state.teaching_scope() as application:
        yield application


Application = Annotated[TeachingAssistantApplication, Depends(get_application)]


@router.get(
    "/shared-knowledge-bases/{kb_id}/teaching-settings",
    response_model=TeachingSettings,
    operation_id="get_teaching_settings",
)
def settings(kb_id: UUID, current: CurrentSessionDependency, application: Application):
    return application.settings(current.user.user_id, kb_id)


@router.patch(
    "/shared-knowledge-bases/{kb_id}/teaching-settings",
    response_model=TeachingSettings,
    operation_id="update_teaching_settings",
)
def update_settings(
    kb_id: UUID,
    payload: UpdateTeachingSettings,
    current: CurrentSessionDependency,
    application: Application,
    idempotency_key: IdempotencyKey,
):
    return application.update_settings(
        current.user.user_id, kb_id, payload.model_dump(mode="json"), idempotency_key
    )


@router.get(
    "/shared-knowledge-bases/{kb_id}/teaching-activities",
    response_model=TeachingActivityList,
    operation_id="list_teaching_activities",
)
def activities(kb_id: UUID, current: CurrentSessionDependency, application: Application):
    return {"items": application.list(current.user.user_id, kb_id)}


@router.post(
    "/shared-knowledge-bases/{kb_id}/teaching-activities",
    response_model=TeachingActivity,
    operation_id="create_teaching_activity",
    status_code=201,
)
def create(
    kb_id: UUID,
    payload: CreateTeachingActivity,
    current: CurrentSessionDependency,
    application: Application,
    idempotency_key: IdempotencyKey,
):
    return application.create(
        current.user.user_id, kb_id, payload.model_dump(mode="json"), idempotency_key
    )


@router.get(
    "/teaching-activities/{activity_id}",
    response_model=TeachingActivity,
    operation_id="get_teaching_activity",
)
def get(activity_id: UUID, current: CurrentSessionDependency, application: Application):
    return application.get(current.user.user_id, activity_id)


@router.patch(
    "/teaching-activities/{activity_id}",
    response_model=TeachingActivity,
    operation_id="update_teaching_activity",
)
def update(
    activity_id: UUID,
    payload: UpdateTeachingActivity,
    current: CurrentSessionDependency,
    application: Application,
    idempotency_key: IdempotencyKey,
):
    return application.update(
        current.user.user_id,
        activity_id,
        payload.model_dump(mode="json", exclude_unset=True),
        idempotency_key,
    )


@router.get(
    "/teaching-activities/{activity_id}/source",
    response_model=TeachingSource,
    operation_id="get_teaching_source",
)
def source(activity_id: UUID, current: CurrentSessionDependency, application: Application):
    return application.source(current.user.user_id, activity_id)


@router.post(
    "/teaching-activities/{activity_id}/run",
    response_model=TeachingActivity,
    operation_id="run_teaching_activity",
    status_code=202,
)
def run(
    activity_id: UUID,
    payload: TeachingVersion,
    current: CurrentSessionDependency,
    application: Application,
    idempotency_key: IdempotencyKey,
    request: Request,
    background: BackgroundTasks,
):
    value, stage = application.start(
        current.user.user_id, activity_id, payload.model_dump(), idempotency_key
    )
    if stage:
        background.add_task(
            request.app.state.execute_teaching, current.user.user_id, activity_id, stage
        )
    return value


@router.post(
    "/teaching-activities/{activity_id}/publish",
    response_model=TeachingActivity,
    operation_id="publish_teaching_activity",
)
def publish(
    activity_id: UUID,
    payload: TeachingVersion,
    current: CurrentSessionDependency,
    application: Application,
    idempotency_key: IdempotencyKey,
):
    return application.publish(
        current.user.user_id, activity_id, payload.model_dump(), idempotency_key
    )


@router.get(
    "/shared-knowledge-bases/{kb_id}/learning-summary",
    response_model=LearningSummary,
    operation_id="get_learning_summary",
)
def summary(kb_id: UUID, current: CurrentSessionDependency, application: Application):
    return application.summary(current.user.user_id, kb_id)
