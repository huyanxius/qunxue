from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import and_, exists, func, or_, select, update
from sqlalchemy.dialects.sqlite import insert

from qunxue_api.modules.agent_memory import (
    MAX_MEMORIES,
    LearningBatch,
    Memory,
    MemoryCandidate,
    MemoryConflict,
    MemorySource,
    context_cost,
    redact_sensitive,
    validate_content,
)

from .agent_conversation_model import AgentConversationRow, AgentMessageRow, AgentRunRow
from .agent_memory_model import MemoryJobRow, MemoryRow, MemoryUsageRow
from .agent_memory_repository import SqliteMemoryRepository, memory_from_row, scope_key, utc

# Reserve before dispatch. The extractor bounds the complete request to 22,000
# UTF-8 bytes and output to 1,500 tokens; failed/unknown usage retains the reserve.
LEARNING_RESERVATION = 24000


class SqliteMemoryLearningRepository(SqliteMemoryRepository):
    def claim(self, *, idle_seconds: int, daily_calls: int, daily_tokens: int):
        now = datetime.now(UTC)
        day = now.date().isoformat()
        latest = (
            select(
                AgentMessageRow.conversation_id,
                func.max(AgentMessageRow.sequence).label("sequence"),
            )
            .where(
                AgentMessageRow.role == "user",
            )
            .group_by(AgentMessageRow.conversation_id)
            .subquery()
        )
        candidates = self.session.execute(
            select(AgentConversationRow, latest.c.sequence)
            .join(latest, latest.c.conversation_id == AgentConversationRow.conversation_id)
            .outerjoin(
                MemoryJobRow, MemoryJobRow.conversation_id == AgentConversationRow.conversation_id
            )
            .outerjoin(
                MemoryUsageRow,
                and_(
                    MemoryUsageRow.user_id == AgentConversationRow.user_id,
                    MemoryUsageRow.day == day,
                ),
            )
            .where(
                func.coalesce(MemoryUsageRow.calls, 0) < daily_calls,
                func.coalesce(MemoryUsageRow.budget_tokens, 0) + LEARNING_RESERVATION
                <= daily_tokens,
                AgentConversationRow.updated_at <= now - timedelta(seconds=idle_seconds),
                latest.c.sequence > func.coalesce(MemoryJobRow.processed_sequence, -1),
                or_(MemoryJobRow.lease_until.is_(None), MemoryJobRow.lease_until < now),
                or_(MemoryJobRow.retry_after.is_(None), MemoryJobRow.retry_after < now),
                or_(
                    MemoryJobRow.attempts.is_(None),
                    MemoryJobRow.attempts < 3,
                    MemoryJobRow.source_sequence < latest.c.sequence,
                ),
                ~exists().where(
                    AgentRunRow.user_id == AgentConversationRow.user_id,
                    AgentRunRow.status == "running",
                ),
            )
            .order_by(AgentConversationRow.updated_at)
            .limit(32)
        ).all()
        for conversation, sequence in candidates:
            user_id = UUID(conversation.user_id)
            task_id = (
                UUID(conversation.current_research_task_id)
                if conversation.current_research_task_id
                else None
            )
            scopes = tuple(
                self.scope(user_id, t) for t in ((None, task_id) if task_id else (None,))
            )
            self.session.execute(
                insert(MemoryJobRow)
                .values(
                    conversation_id=conversation.conversation_id,
                    processed_sequence=-1,
                    attempts=0,
                    source_sequence=-1,
                )
                .on_conflict_do_nothing()
            )
            job = self.session.get(
                MemoryJobRow, conversation.conversation_id, populate_existing=True
            )
            if not any(s.learn_memory for s in scopes):
                job.processed_sequence = sequence
                continue
            rows = self.session.scalars(
                select(AgentMessageRow)
                .where(
                    AgentMessageRow.conversation_id == conversation.conversation_id,
                    AgentMessageRow.sequence > job.processed_sequence,
                    AgentMessageRow.role == "user",
                )
                .order_by(AgentMessageRow.sequence)
                .limit(16)
            ).all()
            sources, used, through = [], 0, job.processed_sequence
            for row in rows:
                size = context_cost(row.content)
                if size <= 10000 and used + size > 12000:
                    break
                through = row.sequence
                if size > 10000:
                    continue
                sources.append(
                    MemorySource(
                        UUID(row.message_id), row.content, utc(row.created_at), row.sequence
                    )
                )
                used += size
            if not sources:
                job.processed_sequence = through
                continue
            self.session.execute(
                insert(MemoryUsageRow)
                .values(
                    user_id=str(user_id),
                    day=day,
                    calls=0,
                    input_tokens=0,
                    output_tokens=0,
                    budget_tokens=0,
                )
                .on_conflict_do_nothing()
            )
            reserved = self.session.execute(
                update(MemoryUsageRow)
                .where(
                    MemoryUsageRow.user_id == str(user_id),
                    MemoryUsageRow.day == day,
                    MemoryUsageRow.calls < daily_calls,
                    MemoryUsageRow.budget_tokens + LEARNING_RESERVATION <= daily_tokens,
                )
                .values(
                    calls=MemoryUsageRow.calls + 1,
                    budget_tokens=MemoryUsageRow.budget_tokens + LEARNING_RESERVATION,
                )
            )
            if reserved.rowcount != 1:
                continue
            token = str(uuid4())
            claimed = self.session.execute(
                update(MemoryJobRow)
                .where(
                    MemoryJobRow.conversation_id == conversation.conversation_id,
                    MemoryJobRow.processed_sequence == job.processed_sequence,
                    or_(MemoryJobRow.lease_until.is_(None), MemoryJobRow.lease_until < now),
                )
                .values(
                    lease_token=token,
                    lease_until=now + timedelta(minutes=5),
                    # Retry only when genuinely new input arrives, not merely
                    # because an existing backlog spans more than one batch.
                    source_sequence=sequence,
                    attempts=1 if job.source_sequence != sequence else job.attempts + 1,
                )
                .execution_options(synchronize_session=False)
            )
            if claimed.rowcount != 1:
                raise MemoryConflict("后台记忆任务已被领取")
            memories, used = [], 0
            for scope in scopes:
                for item in self.list(user_id, scope.task_id):
                    size = context_cost(item.content) + 160
                    if used + size <= 4000:
                        memories.append(item)
                        used += size
            return LearningBatch(
                UUID(conversation.conversation_id),
                user_id,
                task_id,
                token,
                through,
                tuple(sources),
                scopes,
                tuple(memories),
                day,
            )
        return None

    def complete(
        self,
        batch: LearningBatch,
        candidates: tuple[MemoryCandidate, ...],
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        now = datetime.now(UTC)
        job = self.session.get(MemoryJobRow, str(batch.conversation_id), populate_existing=True)
        if job is None or job.lease_token != batch.lease_token or utc(job.lease_until) <= now:
            return
        # Check and acquire the job inside the same write transaction as the merge.
        claimed = self.session.execute(
            update(MemoryJobRow)
            .where(
                MemoryJobRow.conversation_id == str(batch.conversation_id),
                MemoryJobRow.lease_token == batch.lease_token,
                MemoryJobRow.lease_until > now,
            )
            .values(
                processed_sequence=batch.through_sequence,
                lease_token=None,
                lease_until=None,
                retry_after=None,
                attempts=0,
                last_error=None,
            )
            .execution_options(synchronize_session=False)
        )
        if claimed.rowcount != 1:
            return
        sources = {s.message_id: s for s in batch.sources}
        for snapshot in batch.scopes:
            current = self.scope(batch.user_id, snapshot.task_id)
            if current.version != snapshot.version or not current.learn_memory:
                continue
            pending: dict[str, Memory] = {}
            scope_name = "project" if snapshot.task_id else "user"
            # Model output order is not source order. Keep the newest valid
            # evidence for each key when a batch includes a correction.
            ordered_candidates = sorted(
                candidates[:8],
                key=lambda c: (
                    (
                        sources[c.source_message_id].created_at,
                        sources[c.source_message_id].sequence,
                    )
                    if c.source_message_id in sources
                    else (datetime.min.replace(tzinfo=UTC), 0)
                ),
                reverse=True,
            )
            for candidate in ordered_candidates:
                if candidate.scope != scope_name:
                    continue
                source = sources.get(candidate.source_message_id)
                if (
                    source is None
                    or not candidate.source_quote.strip()
                    or candidate.source_quote not in source.content
                    or redact_sensitive(candidate.source_quote) != candidate.source_quote
                    or (
                        current.learn_after is not None and source.created_at <= current.learn_after
                    )
                ):
                    continue
                try:
                    key, content = validate_content(candidate.key, candidate.content)
                except ValueError:
                    continue
                row = self.session.scalar(
                    select(MemoryRow).where(
                        MemoryRow.user_id == str(batch.user_id),
                        MemoryRow.scope_key == scope_key(snapshot.task_id),
                        MemoryRow.key == key,
                    )
                )
                old = memory_from_row(row) if row else None
                if old and (old.deleted or old.origin != "learned"):
                    continue
                if key in pending:
                    continue
                if old:
                    old_source_time = self.session.scalar(
                        select(AgentMessageRow.created_at).where(
                            AgentMessageRow.message_id == str(old.source_message_id)
                        )
                    )
                    # Processing order is not evidence order: an old conversation
                    # must not overwrite a preference learned from a newer one.
                    if source.created_at <= utc(old_source_time or old.updated_at):
                        continue
                if (
                    not old
                    and len(self.list(batch.user_id, snapshot.task_id)) + len(pending)
                    >= MAX_MEMORIES
                ):
                    continue
                pending[key] = Memory(
                    memory_id=old.memory_id if old else uuid4(),
                    user_id=batch.user_id,
                    task_id=snapshot.task_id,
                    key=key,
                    content=content,
                    origin="learned",
                    version=old.version + 1 if old else 1,
                    created_at=old.created_at if old else now,
                    updated_at=now,
                    source_conversation_id=batch.conversation_id,
                    source_message_id=source.message_id,
                    source_quote=candidate.source_quote[:1000],
                )
            if pending:
                self.lock_scope(current)
                for memory in pending.values():
                    self.store(memory)
        total = max(0, input_tokens) + max(0, output_tokens)
        usage = self.session.get(MemoryUsageRow, (str(batch.user_id), batch.usage_day))
        if usage is not None:
            usage.input_tokens += max(0, input_tokens)
            usage.output_tokens += max(0, output_tokens)
            if total:
                usage.budget_tokens += total - LEARNING_RESERVATION

    def failed(self, batch: LearningBatch) -> None:
        self.session.execute(
            update(MemoryJobRow)
            .where(
                MemoryJobRow.conversation_id == str(batch.conversation_id),
                MemoryJobRow.lease_token == batch.lease_token,
            )
            .values(
                lease_token=None,
                lease_until=None,
                retry_after=datetime.now(UTC) + timedelta(minutes=15),
                last_error="extraction_failed",
            )
        )
