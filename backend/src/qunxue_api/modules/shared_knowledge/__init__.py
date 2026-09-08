"""Course reference collections; membership never grants access to private research."""

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from secrets import token_urlsafe
from typing import Protocol
from uuid import UUID, uuid4


class SharedKnowledgeValidationError(ValueError):
    pass


class SharedKnowledgeUnavailable(LookupError):
    def __init__(self, message="课程资料不存在或已停止共享，请重新选择知识来源。"):
        super().__init__(message)


class SharedKnowledgeForbidden(PermissionError):
    def __init__(self):
        super().__init__("只有创建者可以管理课程资料。")


@dataclass(frozen=True)
class SharedKnowledgeBase:
    id: UUID
    owner_user_id: UUID
    name: str
    description: str
    share_token: str
    sharing_enabled: bool = False
    deleted_at: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class SharedDocument:
    # Independent document identity is necessary because research materials require a task.
    # Blocks and locators still come from the common parser; collections store only links.
    id: UUID
    owner_user_id: UUID
    filename: str
    media_type: str
    content_hash: str
    size_bytes: int
    parse_id: UUID
    status: str
    segments: tuple[dict, ...] = ()
    error_message: str | None = None
    warnings: tuple[str, ...] = ()
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    knowledge_status: str = "queued"
    knowledge: dict | None = None
    knowledge_error: str | None = None
    index_status: str = "queued"
    index_error: str | None = None


class SharedKnowledgeRepository(Protocol):
    def get(self, kb_id: UUID) -> SharedKnowledgeBase | None: ...
    def save(self, kb: SharedKnowledgeBase, *, request_key: str | None = None) -> None: ...
    def find_request(self, user_id: UUID, key: str) -> SharedKnowledgeBase | None: ...
    def list_for(self, user_id: UUID) -> tuple[SharedKnowledgeBase, ...]: ...
    def find_token(self, token: str) -> SharedKnowledgeBase | None: ...
    def subscribed(self, user_id: UUID, kb_id: UUID) -> bool: ...
    def subscribe(self, user_id: UUID, kb_id: UUID) -> bool: ...
    def unsubscribe(self, user_id: UUID, kb_id: UUID) -> None: ...
    def documents(self, kb_id: UUID) -> tuple[SharedDocument, ...]: ...
    def detach(self, kb_id: UUID, document_id: UUID | None = None) -> None: ...
    def commit(self) -> None: ...


class SharedKnowledgeService:
    def __init__(self, repository: SharedKnowledgeRepository):
        self.repository = repository

    def require_read(self, user_id: UUID, kb_id: UUID) -> SharedKnowledgeBase:
        kb = self.repository.get(kb_id)
        if kb is None or kb.deleted_at:
            raise SharedKnowledgeUnavailable()
        if kb.owner_user_id != user_id and not (
            kb.sharing_enabled and self.repository.subscribed(user_id, kb_id)
        ):
            raise SharedKnowledgeUnavailable()
        return kb

    def require_manage(self, user_id: UUID, kb_id: UUID) -> SharedKnowledgeBase:
        kb = self.require_read(user_id, kb_id)
        if kb.owner_user_id != user_id:
            raise SharedKnowledgeForbidden()
        return kb

    def create(self, user_id: UUID, name: str, description: str, request_key: str):
        existing = self.repository.find_request(user_id, request_key)
        if existing:
            return existing
        kb = SharedKnowledgeBase(
            uuid4(), user_id, name.strip(), description.strip(), token_urlsafe(32)
        )
        self.repository.save(kb, request_key=request_key)
        self.repository.commit()
        return self.repository.find_request(user_id, request_key)

    def update(self, user_id: UUID, kb_id: UUID, **changes):
        kb = self.require_manage(user_id, kb_id)
        allowed = {
            key: value
            for key, value in changes.items()
            if key in {"name", "description", "sharing_enabled"} and value is not None
        }
        kb = replace(kb, **allowed, updated_at=datetime.now(UTC))
        self.repository.save(kb)
        self.repository.commit()
        return kb

    def delete(self, user_id: UUID, kb_id: UUID):
        kb = self.repository.get(kb_id)
        if kb is None or kb.owner_user_id != user_id:
            raise SharedKnowledgeUnavailable()
        self.repository.save(replace(kb, deleted_at=datetime.now(UTC), sharing_enabled=False))
        self.repository.detach(kb_id)
        self.repository.commit()

    def join(self, user_id: UUID, token: str):
        kb = self.repository.find_token(token)
        if kb is None or kb.deleted_at or not kb.sharing_enabled:
            raise SharedKnowledgeUnavailable("链接无效或已关闭。")
        added = False if kb.owner_user_id == user_id else self.repository.subscribe(user_id, kb.id)
        self.repository.commit()
        return kb, added

    def leave(self, user_id: UUID, kb_id: UUID):
        self.repository.unsubscribe(user_id, kb_id)
        self.repository.commit()

    def documents(self, user_id: UUID, kb_id: UUID, *, ready_only=False):
        kb = self.require_read(user_id, kb_id)
        return tuple(
            doc
            for doc in self.repository.documents(kb_id)
            if doc.owner_user_id == kb.owner_user_id
            and (not ready_only and user_id == kb.owner_user_id or doc.status == "ready")
        )

    def source(self, user_id: UUID, kb_id: UUID, document_id: UUID, segment_id: str | None = None):
        doc = next(
            (
                doc
                for doc in self.documents(user_id, kb_id)
                if doc.id == document_id and doc.status == "ready"
            ),
            None,
        )
        if doc is None:
            raise SharedKnowledgeUnavailable()
        if segment_id and not any(item["segment_id"] == segment_id for item in doc.segments):
            raise SharedKnowledgeUnavailable()
        return doc

    def detach(self, user_id: UUID, kb_id: UUID, document_id: UUID):
        self.require_manage(user_id, kb_id)
        self.repository.detach(kb_id, document_id)
        self.repository.commit()
