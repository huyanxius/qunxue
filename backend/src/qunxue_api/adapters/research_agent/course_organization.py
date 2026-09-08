"""Recoverable course processing; model calls never hold a SQLite write transaction."""

import logging
import math
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import or_, select, update

from qunxue_api.adapters.sqlite.shared_knowledge import (
    SharedDocumentRow,
    SharedKnowledgeBaseRow,
    SharedKnowledgeDocumentRow,
    _document,
)

from .course_knowledge import (
    CourseKnowledgeGenerator,
    CourseOrganizationError,
    CourseWorkCancelled,
    validate_knowledge,
)

logger = logging.getLogger(__name__)


class CourseOrganizationWorker:
    def __init__(self, database, *, generate=None, embedder=None, embedding_model=None):
        self.database = database
        self.generate, self.embedder, self.embedding_model = generate, embedder, embedding_model

    def run_once(self):
        now, token = datetime.now(UTC), str(uuid4())
        live_ids = (
            select(SharedKnowledgeDocumentRow.document_id)
            .join(
                SharedKnowledgeBaseRow,
                SharedKnowledgeBaseRow.id == SharedKnowledgeDocumentRow.knowledge_base_id,
            )
            .where(SharedKnowledgeBaseRow.deleted_at.is_(None))
        )
        with self.database.session() as session:
            row = session.scalar(
                select(SharedDocumentRow)
                .where(
                    SharedDocumentRow.id.in_(live_ids),
                    SharedDocumentRow.status == "ready",
                    or_(
                        SharedDocumentRow.job_token.is_(None),
                        SharedDocumentRow.job_started_at < now - timedelta(minutes=20),
                    ),
                    or_(
                        SharedDocumentRow.knowledge_status.in_(["queued", "running"]),
                        SharedDocumentRow.index_status.in_(["queued", "running"]),
                    ),
                )
                .order_by(SharedDocumentRow.created_at)
                .limit(1)
            )
            if row is None:
                return False
            stage = "knowledge" if row.knowledge_status in ("queued", "running") else "index"
            claimed = session.execute(
                update(SharedDocumentRow)
                .where(
                    SharedDocumentRow.id == row.id,
                    or_(
                        SharedDocumentRow.job_token.is_(None),
                        SharedDocumentRow.job_started_at < now - timedelta(minutes=20),
                    ),
                )
                .values(job_token=token, job_started_at=now, **{f"{stage}_status": "running"})
            )
            if not claimed.rowcount:
                return False
            document, vectors = _document(row), dict(row.vectors)
            checkpoints = dict(row.knowledge_checkpoints or {})
            session.commit()
        result, error = None, None
        try:
            if stage == "knowledge":
                if self.generate is None:
                    raise RuntimeError("model not configured")
                if isinstance(self.generate, CourseKnowledgeGenerator):

                    def checkpoint(value):
                        with self.database.session() as current:
                            saved = current.execute(
                                update(SharedDocumentRow)
                                .where(
                                    SharedDocumentRow.id == str(document.id),
                                    SharedDocumentRow.id.in_(live_ids),
                                    SharedDocumentRow.job_token == token,
                                )
                                .values(
                                    knowledge_checkpoints=value, job_started_at=datetime.now(UTC)
                                )
                            )
                            if not saved.rowcount:
                                raise CourseWorkCancelled()
                            current.commit()

                    result = self.generate(
                        document, checkpoints=checkpoints, on_checkpoint=checkpoint
                    )
                else:
                    result = validate_knowledge(self.generate(document), document)
            else:
                if self.embedder is None or not self.embedding_model:
                    raise RuntimeError("embedding not configured")
                cached = dict(vectors.get(self.embedding_model, {}))
                dimension = len(next(iter(cached.values()))) if cached else None
                missing = [
                    s
                    for s in document.segments
                    if f"material:{document.id}:{s['segment_id']}" not in cached
                ]
                for start in range(0, len(missing), 16):
                    batch = missing[start : start + 16]
                    values = self.embedder.embed_documents([s["text"] for s in batch])
                    if len(values) != len(batch):
                        raise ValueError("invalid vector count")
                    for segment, vector in zip(batch, values, strict=True):
                        if (
                            not vector
                            or not all(math.isfinite(v) for v in vector)
                            or not any(vector)
                        ):
                            raise ValueError("invalid vector")
                        if dimension is None:
                            dimension = len(vector)
                        if len(vector) != dimension:
                            raise ValueError("inconsistent vector dimensions")
                        cached[f"material:{document.id}:{segment['segment_id']}"] = list(vector)
                    # Retry keeps completed batches instead of starting the file again.
                    with self.database.session() as session:
                        session.execute(
                            update(SharedDocumentRow)
                            .where(
                                SharedDocumentRow.id == str(document.id),
                                SharedDocumentRow.job_token == token,
                            )
                            .values(vectors={**vectors, self.embedding_model: cached})
                        )
                        session.commit()
                result = {**vectors, self.embedding_model: cached}
        except CourseWorkCancelled:
            return True
        except Exception as failure:
            logger.warning(
                "Course processing failed document=%s stage=%s type=%s code=%s",
                document.id,
                stage,
                type(failure).__name__,
                getattr(failure, "code", "internal_error"),
            )
            # Raw provider messages can contain credentials; expose only classified errors.
            error = (
                str(failure)
                if isinstance(failure, CourseOrganizationError)
                else str(CourseOrganizationError("internal_error"))
                if stage == "knowledge"
                else "语义索引失败，请检查 embedding 配置或服务后重试。"
            )
        with self.database.session() as session:
            values = {
                f"{stage}_status": "failed" if error else "ready",
                f"{stage}_error": error,
                "job_token": None,
                "job_started_at": None,
            }
            if not error:
                values["knowledge" if stage == "knowledge" else "vectors"] = result
            session.execute(
                update(SharedDocumentRow)
                .where(
                    SharedDocumentRow.id == str(document.id),
                    SharedDocumentRow.job_token == token,
                )
                .values(**values)
            )
            session.commit()
        return True
