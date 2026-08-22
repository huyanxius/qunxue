from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, or_, select, update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from qunxue_api.adapters.sqlite import ModelInvocationRow, ResearchTaskRow
from qunxue_api.modules.research_intake import (
    EntryType,
    ResearchTask,
    ResearchTaskRepository,
    ResearchTaskStatus,
)


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class SqliteResearchTaskRepository(ResearchTaskRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, task_id: UUID, user_id: UUID) -> ResearchTask | None:
        row = self._session.scalar(
            select(ResearchTaskRow).where(
                ResearchTaskRow.task_id == str(task_id),
                ResearchTaskRow.user_id == str(user_id),
            )
        )
        return self._to_domain(row) if row is not None else None

    def list_for_user(self, user_id: UUID, *, limit: int) -> list[ResearchTask]:
        rows = self._session.scalars(
            select(ResearchTaskRow)
            .where(ResearchTaskRow.user_id == str(user_id))
            .order_by(ResearchTaskRow.updated_at.desc(), ResearchTaskRow.task_id.desc())
            .limit(limit)
        )
        return [self._to_domain(row) for row in rows]

    def delete(self, task_id: UUID, user_id: UUID) -> ResearchTask | None:
        row = self._session.scalar(
            select(ResearchTaskRow).where(
                ResearchTaskRow.task_id == str(task_id),
                ResearchTaskRow.user_id == str(user_id),
            )
        )
        if row is None:
            return None
        task = self._to_domain(row)
        self._session.execute(
            delete(ModelInvocationRow).where(
                ModelInvocationRow.task_id == str(task_id),
            )
        )
        self._session.delete(row)
        self._session.flush()
        return task

    def add_or_get_by_idempotency_key(self, task: ResearchTask) -> ResearchTask:
        statement = (
            insert(ResearchTaskRow)
            .values(
                task_id=str(task.task_id),
                user_id=str(task.user_id),
                entry_type=task.entry_type.value,
                status=task.status.value,
                version=task.version,
                idempotency_key=task.idempotency_key,
                seed_theory_id=task.seed_theory_id,
                seed_theory_name=task.seed_theory_name,
                phenomenon_query_id=(
                    str(task.phenomenon_query_id) if task.phenomenon_query_id else None
                ),
                phenomenon_version=task.phenomenon_version,
                phenomenon_summary=task.phenomenon_summary,
                phenomenon_research_intent=task.phenomenon_research_intent,
                adopted_theory_count=task.adopted_theory_count,
                current_phenomenon_candidate_id=(
                    str(task.current_phenomenon_candidate_id)
                    if task.current_phenomenon_candidate_id
                    else None
                ),
                current_material_intake_run_id=(
                    str(task.current_material_intake_run_id)
                    if task.current_material_intake_run_id
                    else None
                ),
                current_match_run_id=(
                    str(task.current_match_run_id) if task.current_match_run_id else None
                ),
                current_theory_plan_id=(
                    str(task.current_theory_plan_id)
                    if task.current_theory_plan_id
                    else None
                ),
                current_framework_id=(
                    str(task.current_framework_id) if task.current_framework_id else None
                ),
                knowledge_release_id=task.knowledge_release_id,
                conversation_id=(str(task.conversation_id) if task.conversation_id else None),
                source_turn_id=(str(task.source_turn_id) if task.source_turn_id else None),
                source_agent_run_id=(
                    str(task.source_agent_run_id) if task.source_agent_run_id else None
                ),
                created_at=task.created_at,
                updated_at=task.updated_at,
            )
            .on_conflict_do_nothing(index_elements=["user_id", "idempotency_key"])
        )
        self._session.execute(statement)

        row = self._session.scalar(
            select(ResearchTaskRow).where(
                ResearchTaskRow.user_id == str(task.user_id),
                ResearchTaskRow.idempotency_key == task.idempotency_key,
            )
        )
        if row is None:
            raise RuntimeError("research task insert did not return a persisted row")
        return self._to_domain(row)

    def save_progress(self, task: ResearchTask) -> ResearchTask | None:
        result = self._session.execute(
            update(ResearchTaskRow)
            .where(
                ResearchTaskRow.task_id == str(task.task_id),
                ResearchTaskRow.user_id == str(task.user_id),
                or_(
                    ResearchTaskRow.version == task.version - 1,
                    (
                        # Legacy projection writers persisted an initial task
                        # snapshot with an externally supplied version and
                        # timestamp. Only an untouched DRAFT row can use this
                        # compatibility path; real transitions increment the
                        # version and update the timestamp together.
                        (ResearchTaskRow.version == 1)
                        & (ResearchTaskRow.status == ResearchTaskStatus.DRAFT.value)
                        & (ResearchTaskRow.created_at == ResearchTaskRow.updated_at)
                    ),
                ),
            )
            .values(
                status=task.status.value,
                version=task.version,
                updated_at=task.updated_at,
                phenomenon_query_id=(
                    str(task.phenomenon_query_id) if task.phenomenon_query_id else None
                ),
                phenomenon_version=task.phenomenon_version,
                phenomenon_summary=task.phenomenon_summary,
                phenomenon_research_intent=task.phenomenon_research_intent,
                adopted_theory_count=task.adopted_theory_count,
                current_phenomenon_candidate_id=(
                    str(task.current_phenomenon_candidate_id)
                    if task.current_phenomenon_candidate_id
                    else None
                ),
                current_material_intake_run_id=(
                    str(task.current_material_intake_run_id)
                    if task.current_material_intake_run_id
                    else None
                ),
                current_match_run_id=(
                    str(task.current_match_run_id) if task.current_match_run_id else None
                ),
                current_theory_plan_id=(
                    str(task.current_theory_plan_id)
                    if task.current_theory_plan_id
                    else None
                ),
                current_framework_id=(
                    str(task.current_framework_id) if task.current_framework_id else None
                ),
                knowledge_release_id=task.knowledge_release_id,
                conversation_id=(str(task.conversation_id) if task.conversation_id else None),
                source_turn_id=(str(task.source_turn_id) if task.source_turn_id else None),
                source_agent_run_id=(
                    str(task.source_agent_run_id) if task.source_agent_run_id else None
                ),
            )
        )
        if result.rowcount != 1:
            return None
        self._session.expire_all()
        persisted = self._session.get(ResearchTaskRow, str(task.task_id))
        return self._to_domain(persisted) if persisted is not None else None

    @staticmethod
    def _to_domain(row: ResearchTaskRow) -> ResearchTask:
        if row.user_id is None:
            raise RuntimeError("legacy research task has no owner and cannot enter the domain")
        return ResearchTask(
            task_id=UUID(row.task_id),
            user_id=UUID(row.user_id),
            entry_type=EntryType(row.entry_type),
            status=ResearchTaskStatus(row.status),
            version=row.version,
            idempotency_key=row.idempotency_key,
            seed_theory_id=row.seed_theory_id,
            seed_theory_name=row.seed_theory_name,
            created_at=_as_utc(row.created_at),
            updated_at=_as_utc(row.updated_at),
            phenomenon_query_id=(
                UUID(row.phenomenon_query_id) if row.phenomenon_query_id else None
            ),
            phenomenon_version=row.phenomenon_version,
            phenomenon_summary=row.phenomenon_summary,
            phenomenon_research_intent=row.phenomenon_research_intent,
            adopted_theory_count=row.adopted_theory_count,
            current_phenomenon_candidate_id=(
                UUID(row.current_phenomenon_candidate_id)
                if row.current_phenomenon_candidate_id
                else None
            ),
            current_material_intake_run_id=(
                UUID(row.current_material_intake_run_id)
                if row.current_material_intake_run_id
                else None
            ),
            current_match_run_id=(
                UUID(row.current_match_run_id) if row.current_match_run_id else None
            ),
            current_theory_plan_id=(
                UUID(row.current_theory_plan_id) if row.current_theory_plan_id else None
            ),
            current_framework_id=(
                UUID(row.current_framework_id) if row.current_framework_id else None
            ),
            knowledge_release_id=row.knowledge_release_id,
            conversation_id=UUID(row.conversation_id) if row.conversation_id else None,
            source_turn_id=UUID(row.source_turn_id) if row.source_turn_id else None,
            source_agent_run_id=(
                UUID(row.source_agent_run_id) if row.source_agent_run_id else None
            ),
        )
