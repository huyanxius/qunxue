"""Recheck sources already admitted to an in-progress model request."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from uuid import UUID

_material_checks: ContextVar[dict[tuple[UUID, UUID, UUID], Callable[[], bool]] | None] = (
    ContextVar("model_material_checks", default=None)
)


@contextmanager
def model_material_access_scope() -> Iterator[None]:
    if _material_checks.get() is not None:
        yield
        return
    token = _material_checks.set({})
    try:
        yield
    finally:
        _material_checks.reset(token)


def track_material_access(
    material_id: UUID, *, user_id: UUID, task_id: UUID, check: Callable[[], bool]
) -> None:
    checks = _material_checks.get()
    if checks is not None:
        checks[material_id, user_id, task_id] = check


def require_current_model_material_access() -> None:
    checks = _material_checks.get()
    if checks and not all(check() for check in tuple(checks.values())):
        raise ValueError("材料的模型处理许可已变更，请按当前许可重新发起。")
