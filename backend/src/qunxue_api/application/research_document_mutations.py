import json
from dataclasses import dataclass
from hashlib import sha256
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ResearchDocumentMutationReceipt:
    request_id: UUID
    user_id: UUID
    idempotency_key: str
    operation: str
    request_hash: str
    status: str
    result_id: UUID | None = None
    result_version: int | None = None


class ResearchDocumentMutationRepository(Protocol):
    def claim(
        self,
        *,
        user_id: UUID,
        idempotency_key: str,
        operation: str,
        request_hash: str,
    ) -> ResearchDocumentMutationReceipt: ...

    def complete(
        self,
        *,
        request_id: UUID,
        result_id: UUID,
        result_version: int,
    ) -> ResearchDocumentMutationReceipt: ...

    def fail(self, *, request_id: UUID) -> ResearchDocumentMutationReceipt: ...


def mutation_request_hash(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return f"sha256:{sha256(encoded.encode()).hexdigest()}"
