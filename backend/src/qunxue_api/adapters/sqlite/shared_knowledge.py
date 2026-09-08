"""Thin standalone document storage on the existing SQLite database."""

from dataclasses import asdict
from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    delete,
    select,
)
from sqlalchemy.orm import Mapped, mapped_column

from qunxue_api.adapters.sqlite.base import Base
from qunxue_api.modules.shared_knowledge import SharedDocument, SharedKnowledgeBase


class CourseProfileRow(Base):
    __tablename__ = "course_profiles"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), primary_key=True)
    role: Mapped[str] = mapped_column(String(16))
    guide_dismissed: Mapped[bool] = mapped_column(Boolean, default=False)


class SharedKnowledgeBaseRow(Base):
    __tablename__ = "shared_knowledge_bases"
    __table_args__ = (UniqueConstraint("owner_user_id", "request_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), index=True)
    request_key: Mapped[str] = mapped_column(String(128))
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text)
    share_token: Mapped[str] = mapped_column(String(128), unique=True)
    sharing_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SharedKnowledgeSubscriptionRow(Base):
    __tablename__ = "shared_knowledge_subscriptions"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), primary_key=True)
    knowledge_base_id: Mapped[str] = mapped_column(
        ForeignKey("shared_knowledge_bases.id"), primary_key=True
    )


class SharedDocumentRow(Base):
    __tablename__ = "shared_documents"
    __table_args__ = (UniqueConstraint("owner_user_id", "request_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), index=True)
    request_key: Mapped[str] = mapped_column(String(128))
    filename: Mapped[str] = mapped_column(String(512))
    media_type: Mapped[str] = mapped_column(String(128))
    content_hash: Mapped[str] = mapped_column(String(64))
    content: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
    size_bytes: Mapped[int] = mapped_column(Integer)
    parse_id: Mapped[str] = mapped_column(String(36))
    status: Mapped[str] = mapped_column(String(32))
    segments: Mapped[list] = mapped_column(JSON)
    vectors: Mapped[dict] = mapped_column(JSON, default=dict)
    knowledge_status: Mapped[str] = mapped_column(String(16), default="queued")
    knowledge: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    knowledge_error: Mapped[str | None] = mapped_column(Text)
    index_status: Mapped[str] = mapped_column(String(16), default="queued")
    index_error: Mapped[str | None] = mapped_column(Text)
    job_token: Mapped[str | None] = mapped_column(String(36))
    job_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SharedKnowledgeDocumentRow(Base):
    __tablename__ = "shared_knowledge_documents"
    knowledge_base_id: Mapped[str] = mapped_column(
        ForeignKey("shared_knowledge_bases.id"), primary_key=True
    )
    document_id: Mapped[str] = mapped_column(
        ForeignKey("shared_documents.id"), primary_key=True, index=True
    )


def _kb(row):
    return SharedKnowledgeBase(
        **{
            key: UUID(getattr(row, key)) if key in {"id", "owner_user_id"} else getattr(row, key)
            for key in SharedKnowledgeBase.__dataclass_fields__
        }
    )


def _document(row):
    return SharedDocument(
        id=UUID(row.id),
        owner_user_id=UUID(row.owner_user_id),
        filename=row.filename,
        media_type=row.media_type,
        content_hash=row.content_hash,
        size_bytes=row.size_bytes,
        parse_id=UUID(row.parse_id),
        status=row.status,
        segments=tuple(row.segments),
        error_message=row.error_message,
        warnings=tuple(row.warnings),
        created_at=row.created_at,
        knowledge_status=row.knowledge_status,
        knowledge=row.knowledge,
        knowledge_error=row.knowledge_error,
        index_status=row.index_status,
        index_error=row.index_error,
    )


class SqliteSharedKnowledgeRepository:
    def __init__(self, session):
        self.session = session

    def course_role(self, user_id):
        row = self.session.get(CourseProfileRow, str(user_id))
        return row.role if row else None

    def course_guide_dismissed(self, user_id):
        row = self.session.get(CourseProfileRow, str(user_id))
        return bool(row and row.guide_dismissed)

    def set_course_role(self, user_id, role, guide_dismissed=False):
        self.session.merge(
            CourseProfileRow(user_id=str(user_id), role=role, guide_dismissed=guide_dismissed)
        )
        self.commit()
        return role

    def retry_document(self, document_id):
        row = self.session.get(SharedDocumentRow, str(document_id))
        # Active work is left alone; retries cannot invalidate a running worker lease.
        for stage in ("knowledge", "index"):
            if getattr(row, f"{stage}_status") == "failed":
                setattr(row, f"{stage}_status", "queued")
                setattr(row, f"{stage}_error", None)
        self.commit()
        return _document(row)

    def commit(self):
        self.session.commit()

    def get(self, kb_id):
        row = self.session.get(SharedKnowledgeBaseRow, str(kb_id), populate_existing=True)
        return _kb(row) if row else None

    def save(self, kb, *, request_key=None):
        values = {
            key: str(value) if isinstance(value, UUID) else value
            for key, value in asdict(kb).items()
        }
        if request_key is not None:
            from sqlalchemy.dialects.sqlite import insert

            self.session.execute(
                insert(SharedKnowledgeBaseRow)
                .values(**values, request_key=request_key)
                .on_conflict_do_nothing(index_elements=["owner_user_id", "request_key"])
            )
        else:
            row = self.session.get(SharedKnowledgeBaseRow, str(kb.id))
            for key, value in values.items():
                setattr(row, key, value)
        self.session.flush()

    def find_request(self, user_id, key):
        row = self.session.scalar(
            select(SharedKnowledgeBaseRow).where(
                SharedKnowledgeBaseRow.owner_user_id == str(user_id),
                SharedKnowledgeBaseRow.request_key == key,
            )
        )
        return _kb(row) if row else None

    def list_for(self, user_id):
        subscribed = select(SharedKnowledgeSubscriptionRow.knowledge_base_id).where(
            SharedKnowledgeSubscriptionRow.user_id == str(user_id)
        )
        rows = self.session.scalars(
            select(SharedKnowledgeBaseRow)
            .where(
                (
                    (SharedKnowledgeBaseRow.owner_user_id == str(user_id))
                    & SharedKnowledgeBaseRow.deleted_at.is_(None)
                )
                | SharedKnowledgeBaseRow.id.in_(subscribed)
            )
            .order_by(SharedKnowledgeBaseRow.updated_at.desc())
        )
        return tuple(_kb(row) for row in rows)

    def find_token(self, token):
        row = self.session.scalar(
            select(SharedKnowledgeBaseRow).where(SharedKnowledgeBaseRow.share_token == token)
        )
        return _kb(row) if row else None

    def subscribed(self, user_id, kb_id):
        return (
            self.session.get(SharedKnowledgeSubscriptionRow, (str(user_id), str(kb_id))) is not None
        )

    def subscribe(self, user_id, kb_id):
        from sqlalchemy.dialects.sqlite import insert

        result = self.session.execute(
            insert(SharedKnowledgeSubscriptionRow)
            .values(user_id=str(user_id), knowledge_base_id=str(kb_id))
            .on_conflict_do_nothing()
        )
        return result.rowcount == 1

    def unsubscribe(self, user_id, kb_id):
        self.session.execute(
            delete(SharedKnowledgeSubscriptionRow).where(
                SharedKnowledgeSubscriptionRow.user_id == str(user_id),
                SharedKnowledgeSubscriptionRow.knowledge_base_id == str(kb_id),
            )
        )

    def documents(self, kb_id):
        return tuple(
            _document(row)
            for row in self.session.scalars(
                select(SharedDocumentRow)
                .join(
                    SharedKnowledgeDocumentRow,
                    SharedKnowledgeDocumentRow.document_id == SharedDocumentRow.id,
                )
                .where(SharedKnowledgeDocumentRow.knowledge_base_id == str(kb_id))
                .order_by(SharedDocumentRow.created_at.desc())
            )
        )

    def detach(self, kb_id, document_id=None):
        stmt = delete(SharedKnowledgeDocumentRow).where(
            SharedKnowledgeDocumentRow.knowledge_base_id == str(kb_id)
        )
        if document_id:
            stmt = stmt.where(SharedKnowledgeDocumentRow.document_id == str(document_id))
        self.session.execute(stmt)

    def find_upload(self, user_id, key):
        row = self.session.scalar(
            select(SharedDocumentRow).where(
                SharedDocumentRow.owner_user_id == str(user_id),
                SharedDocumentRow.request_key == key,
            )
        )
        return _document(row) if row else None

    def save_document(self, doc, *, content, request_key, kb_id):
        from sqlalchemy.dialects.sqlite import insert

        values = {
            "id": str(doc.id),
            "owner_user_id": str(doc.owner_user_id),
            "request_key": request_key,
            "filename": doc.filename,
            "media_type": doc.media_type,
            "content_hash": doc.content_hash,
            "content": content,
            "size_bytes": doc.size_bytes,
            "parse_id": str(doc.parse_id),
            "status": doc.status,
            "segments": list(doc.segments),
            "vectors": {},
            "warnings": list(doc.warnings),
            "error_message": doc.error_message,
            "created_at": doc.created_at,
        }
        result = self.session.execute(
            insert(SharedDocumentRow)
            .values(**values)
            .on_conflict_do_nothing(index_elements=["owner_user_id", "request_key"])
        )
        if result.rowcount == 0:
            return self.find_upload(doc.owner_user_id, request_key)
        self.session.add(
            SharedKnowledgeDocumentRow(knowledge_base_id=str(kb_id), document_id=str(doc.id))
        )
        self.session.flush()
        return doc

    def vector_cache(self, documents):
        return SharedDocumentVectorCache(
            self.session, {str(doc.id): doc.content_hash for doc in documents}
        )


class SharedDocumentVectorCache:
    def __init__(self, session, allowed):
        self.session, self.allowed = session, allowed

    def _row(self, chunk):
        document_id = chunk.chunk_id.split(":", 2)[1]
        if document_id not in self.allowed:
            return None
        row = self.session.get(SharedDocumentRow, document_id)
        return row if row and row.content_hash == self.allowed[document_id] else None

    def get_many(self, chunks, model):
        return [
            (row.vectors.get(model, {}).get(chunk.chunk_id) if (row := self._row(chunk)) else None)
            for chunk in chunks
        ]

    def put_many(self, chunks, model, vectors):
        for chunk, vector in zip(chunks, vectors, strict=True):
            row = self._row(chunk)
            if row is not None:
                row.vectors = {
                    **row.vectors,
                    model: {**row.vectors.get(model, {}), chunk.chunk_id: list(vector)},
                }
        self.session.flush()
