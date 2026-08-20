from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from qunxue_api.adapters.sqlite.research_document_model import (
    ResearchDocumentMutationRequestRow,
)


@dataclass(frozen=True, slots=True)
class ResearchDocumentMutationReceipt:
    """Persisted idempotency receipt returned by the SQLite adapter."""

    request_id: UUID
    user_id: UUID
    idempotency_key: str
    operation: str
    request_hash: str
    status: str
    result_id: UUID | None = None
    result_version: int | None = None


class SqliteResearchDocumentMutationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def claim(
        self,
        *,
        user_id: UUID,
        idempotency_key: str,
        operation: str,
        request_hash: str,
    ) -> ResearchDocumentMutationReceipt:
        inserted = self._session.execute(
            insert(ResearchDocumentMutationRequestRow)
            .values(
                request_id=str(uuid4()),
                user_id=str(user_id),
                idempotency_key=idempotency_key,
                operation=operation,
                request_hash=request_hash,
                status="pending",
                created_at=datetime.now(UTC),
            )
            .on_conflict_do_nothing(index_elements=["user_id", "idempotency_key"])
        ).rowcount == 1
        row = self._session.scalar(
            select(ResearchDocumentMutationRequestRow).where(
                ResearchDocumentMutationRequestRow.user_id == str(user_id),
                ResearchDocumentMutationRequestRow.idempotency_key == idempotency_key,
            )
        )
        if row is None:
            raise RuntimeError("document mutation claim was not persisted")
        if row.operation != operation or row.request_hash != request_hash:
            raise ValueError("Idempotency-Key was already used for another document mutation")
        if not inserted:
            if row.status == "failed":
                row.status = "pending"
                self._session.flush()
            elif row.status == "pending":
                raise ValueError("Idempotency-Key is already being processed")
        return _receipt(row)

    def complete(
        self,
        *,
        request_id: UUID,
        result_id: UUID,
        result_version: int,
    ) -> ResearchDocumentMutationReceipt:
        row = self._session.get(ResearchDocumentMutationRequestRow, str(request_id))
        if row is None:
            raise RuntimeError("document mutation claim disappeared")
        row.status = "completed"
        row.result_id = str(result_id)
        row.result_version = result_version
        self._session.flush()
        return _receipt(row)

    def fail(self, *, request_id: UUID) -> ResearchDocumentMutationReceipt:
        row = self._session.get(ResearchDocumentMutationRequestRow, str(request_id))
        if row is None:
            raise RuntimeError("document mutation claim disappeared")
        row.status = "failed"
        self._session.flush()
        return _receipt(row)


def _receipt(row: ResearchDocumentMutationRequestRow) -> ResearchDocumentMutationReceipt:
    return ResearchDocumentMutationReceipt(
        request_id=UUID(row.request_id),
        user_id=UUID(row.user_id),
        idempotency_key=row.idempotency_key,
        operation=row.operation,
        request_hash=row.request_hash,
        status=row.status,
        result_id=UUID(row.result_id) if row.result_id else None,
        result_version=row.result_version,
    )
