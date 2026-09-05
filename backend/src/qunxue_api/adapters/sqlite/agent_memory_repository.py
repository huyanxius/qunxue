import hashlib
import json
from dataclasses import asdict, replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from qunxue_api.modules.agent_memory import (
    PINNED_SCOPE_BUDGET,
    Memory,
    MemoryConflict,
    MemoryNotFound,
    MemoryScope,
    context_cost,
    memory_line,
    validate_content,
)

from .agent_memory_model import MemoryRequestRow, MemoryRevisionRow, MemoryRow, MemoryScopeRow
from .research_intake_model import ResearchTaskRow


def utc(value: datetime | None) -> datetime | None:
    return value.replace(tzinfo=UTC) if value is not None and value.tzinfo is None else value


def scope_key(task_id: UUID | None) -> str:
    return str(task_id) if task_id else "user"


def memory_from_dict(value: dict) -> Memory:
    value = dict(value)
    for key in ("memory_id", "user_id", "task_id", "source_conversation_id", "source_message_id"):
        value[key] = UUID(value[key]) if value.get(key) else None
    for key in ("created_at", "updated_at"):
        value[key] = datetime.fromisoformat(value[key])
    return Memory(**value)


def memory_from_row(row: MemoryRow) -> Memory:
    return Memory(
        memory_id=UUID(row.memory_id),
        user_id=UUID(row.user_id),
        task_id=UUID(row.scope_key) if row.scope_key != "user" else None,
        key=row.key,
        content=row.content,
        origin=row.origin,
        version=row.version,
        created_at=utc(row.created_at),
        updated_at=utc(row.updated_at),
        source_conversation_id=UUID(row.source_conversation_id)
        if row.source_conversation_id
        else None,
        source_message_id=UUID(row.source_message_id) if row.source_message_id else None,
        source_quote=row.source_quote,
        deleted=row.deleted,
    )


class SqliteMemoryRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def scope(self, user_id: UUID, task_id: UUID | None) -> MemoryScope:
        if task_id and not self.session.scalar(
            select(ResearchTaskRow.task_id).where(
                ResearchTaskRow.task_id == str(task_id),
                ResearchTaskRow.user_id == str(user_id),
            )
        ):
            raise MemoryNotFound("项目不存在")
        row = self.session.get(
            MemoryScopeRow, (str(user_id), scope_key(task_id)), populate_existing=True
        )
        if row is None:
            return MemoryScope(user_id=user_id, task_id=task_id)
        return MemoryScope(
            user_id=user_id,
            task_id=task_id,
            version=row.version,
            use_memory=row.use_memory,
            learn_memory=row.learn_memory,
            learn_after=utc(row.learn_after),
        )

    def lock_scope(self, scope: MemoryScope, *, manual: bool = False) -> None:
        self.session.execute(
            insert(MemoryScopeRow)
            .values(
                user_id=str(scope.user_id),
                scope_key=scope_key(scope.task_id),
                task_id=str(scope.task_id) if scope.task_id else None,
                version=0,
                use_memory=True,
                learn_memory=True,
            )
            .on_conflict_do_nothing()
        )
        values = {"version": scope.version + 1}
        if manual:
            # A correction/forget fences every old source in this scope, including
            # conversations that have never been processed by the background worker.
            values["learn_after"] = datetime.now(UTC)
        result = self.session.execute(
            update(MemoryScopeRow)
            .where(
                MemoryScopeRow.user_id == str(scope.user_id),
                MemoryScopeRow.scope_key == scope_key(scope.task_id),
                MemoryScopeRow.version == scope.version,
            )
            .values(**values)
        )
        if result.rowcount != 1:
            raise MemoryConflict("记忆已更新，请重新读取后提交")

    def list(self, user_id: UUID, task_id: UUID | None) -> tuple[Memory, ...]:
        self.scope(user_id, task_id)
        rows = self.session.scalars(
            select(MemoryRow)
            .where(
                MemoryRow.user_id == str(user_id),
                MemoryRow.scope_key == scope_key(task_id),
                MemoryRow.deleted.is_(False),
            )
            .order_by(MemoryRow.updated_at.desc(), MemoryRow.memory_id)
            .limit(100)
        )
        return tuple(memory_from_row(row) for row in rows)

    def get(self, user_id: UUID, memory_id: UUID) -> Memory:
        row = self.session.scalar(
            select(MemoryRow)
            .where(
                MemoryRow.memory_id == str(memory_id),
                MemoryRow.user_id == str(user_id),
                MemoryRow.deleted.is_(False),
            )
            .execution_options(populate_existing=True)
        )
        if row is None:
            raise MemoryNotFound("记忆不存在")
        result = memory_from_row(row)
        self.scope(user_id, result.task_id)
        return result

    def save(
        self,
        *,
        user_id,
        task_id,
        key,
        content,
        origin,
        idempotency_key,
        memory_id=None,
        expected_version=None,
        source_conversation_id=None,
        source_quote=None,
    ) -> Memory:
        key, content = validate_content(key, content)
        scope = self.scope(user_id, task_id)
        fingerprint = hashlib.sha256(
            json.dumps(
                [str(task_id), key, content, origin, str(memory_id), expected_version],
                ensure_ascii=False,
            ).encode()
        ).hexdigest()
        request = self.session.get(MemoryRequestRow, (str(user_id), idempotency_key))
        if request:
            if request.fingerprint != fingerprint:
                raise MemoryConflict("同一请求标识不能用于不同的记忆修改")
            self.get(user_id, UUID(request.memory_id))
            revision = self.session.get(MemoryRevisionRow, (request.memory_id, request.version))
            if revision is None:
                raise MemoryConflict("该记忆已被删除或修订历史不可用")
            return memory_from_dict(revision.snapshot)
        current = self.get(user_id, memory_id) if memory_id else None
        if current and (
            current.task_id != task_id or current.key != key or current.version != expected_version
        ):
            raise MemoryConflict("记忆版本或范围已改变")
        duplicate = self.session.scalar(
            select(MemoryRow).where(
                MemoryRow.user_id == str(user_id),
                MemoryRow.scope_key == scope_key(task_id),
                MemoryRow.key == key,
            )
        )
        if duplicate and (current is None or duplicate.memory_id != str(current.memory_id)):
            raise MemoryConflict("此记忆 key 已存在或已删除，请使用新的 key")
        now = datetime.now(UTC)
        memory = Memory(
            memory_id=current.memory_id if current else uuid4(),
            user_id=user_id,
            task_id=task_id,
            key=key,
            content=content,
            origin=origin,
            version=current.version + 1 if current else 1,
            created_at=current.created_at if current else now,
            updated_at=now,
            source_conversation_id=source_conversation_id,
            source_quote=source_quote,
        )
        entries = tuple(m for m in self.list(user_id, task_id) if m.memory_id != memory.memory_id)
        if len(entries) >= 100:
            raise ValueError("记忆条目已达上限，请先整理已有条目")
        if (
            origin != "learned"
            and sum(
                context_cost(memory_line(m)) for m in (*entries, memory) if m.origin != "learned"
            )
            > PINNED_SCOPE_BUDGET
        ):
            raise ValueError("常驻记忆已达长度上限，请缩短或合并已有条目")
        self.lock_scope(scope, manual=True)
        self.store(memory)
        self.session.add(
            MemoryRequestRow(
                user_id=str(user_id),
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
                memory_id=str(memory.memory_id),
                version=memory.version,
            )
        )
        self.session.flush()
        return memory

    def store(self, memory: Memory) -> None:
        values = asdict(memory)
        values.pop("task_id")
        for key in ("memory_id", "user_id", "source_conversation_id", "source_message_id"):
            values[key] = str(values[key]) if values[key] else None
        values["scope_key"] = scope_key(memory.task_id)
        self.session.merge(MemoryRow(**values))
        self.session.flush()
        snapshot = json.loads(json.dumps(asdict(memory), default=str))
        self.session.add(
            MemoryRevisionRow(
                memory_id=str(memory.memory_id), version=memory.version, snapshot=snapshot
            )
        )
        self.session.flush()

    def delete(self, user_id: UUID, memory_id: UUID, expected_version: int) -> None:
        current = self.get(user_id, memory_id)
        if current.version != expected_version:
            raise MemoryConflict("记忆已更新，请重新读取后删除")
        self.lock_scope(self.scope(user_id, current.task_id), manual=True)
        # The first SELECT does not acquire SQLite's write lock. A human edit
        # may commit before lock_scope; check the entry again inside that lock.
        current = self.get(user_id, memory_id)
        if current.version != expected_version:
            raise MemoryConflict("记忆已更新，请重新读取后删除")
        self.session.execute(
            delete(MemoryRevisionRow).where(MemoryRevisionRow.memory_id == str(memory_id))
        )
        self.store(
            replace(
                current,
                content="",
                source_quote=None,
                source_message_id=None,
                source_conversation_id=None,
                deleted=True,
                version=current.version + 1,
                updated_at=datetime.now(UTC),
            )
        )

    def revisions(self, user_id: UUID, memory_id: UUID) -> tuple[Memory, ...]:
        self.get(user_id, memory_id)
        return tuple(
            memory_from_dict(row.snapshot)
            for row in self.session.scalars(
                select(MemoryRevisionRow)
                .where(MemoryRevisionRow.memory_id == str(memory_id))
                .order_by(MemoryRevisionRow.version.desc())
                .limit(50)
            )
        )

    def configure(self, user_id, task_id, *, expected_version, use_memory, learn_memory):
        scope = self.scope(user_id, task_id)
        if scope.version != expected_version:
            raise MemoryConflict("记忆设置已更新")
        self.lock_scope(scope, manual=True)
        self.session.execute(
            update(MemoryScopeRow)
            .where(
                MemoryScopeRow.user_id == str(user_id),
                MemoryScopeRow.scope_key == scope_key(task_id),
            )
            .values(use_memory=use_memory, learn_memory=learn_memory)
        )
        return self.scope(user_id, task_id)
