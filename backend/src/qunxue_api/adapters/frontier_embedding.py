"""Independent opt-in frontier vectors. Never inherits another model's credentials."""

import math
from dataclasses import dataclass, field
from time import monotonic

import httpx
from sqlalchemy import delete, select
from sqlalchemy.dialects.sqlite import insert

from qunxue_api.adapters.sqlite.frontier_models import (
    FrontierEmbeddingCacheRow,
    FrontierVectorRow,
)
from qunxue_api.modules.frontier_knowledge import SCHEMA_VERSION, content_hash


@dataclass(frozen=True)
class FrontierEmbeddingConfig:
    base_url: str | None = None
    api_key: str | None = field(default=None, repr=False)
    model: str | None = None
    allow_network: bool = False


class FrontierEmbeddingUnavailable(RuntimeError):
    def __init__(self, code="NotConfigured"):
        self.code = code
        super().__init__(code)


class FrontierEmbeddingProvider:
    def __init__(self, config: FrontierEmbeddingConfig, transport=None):
        self.config = config
        self.transport = transport
        self.model = config.model or "not_configured"

    @property
    def status(self):
        if any(
            not isinstance(value, str) or not value.strip()
            for value in (self.config.base_url, self.config.api_key, self.config.model)
        ):
            return "not_configured"
        return "ready" if self.config.allow_network else "network_disabled"

    def embed(self, texts: list[str]) -> list[list[float]]:
        if self.status != "ready":
            raise FrontierEmbeddingUnavailable(
                "NotConfigured" if self.status == "not_configured" else "NetworkDisabled"
            )
        from urllib.parse import urlsplit

        parts = urlsplit(self.config.base_url)
        if (
            parts.scheme != "https"
            or not parts.hostname
            or parts.username
            or parts.password
            or parts.query
            or parts.fragment
        ):
            raise FrontierEmbeddingUnavailable("InvalidEndpoint")
        try:
            with httpx.Client(
                transport=self.transport, timeout=30, follow_redirects=False, trust_env=False
            ) as client:
                response = client.post(
                    self.config.base_url.rstrip("/") + "/embeddings",
                    headers={"Authorization": f"Bearer {self.config.api_key}"},
                    json={"model": self.model, "input": texts},
                )
                response.raise_for_status()
                data = response.json()["data"]
            ordered = sorted(data, key=lambda item: item["index"])
            if [item["index"] for item in ordered] != list(range(len(texts))):
                raise ValueError
            vectors = [validate_vector(item["embedding"]) for item in ordered]
            if len({len(v) for v in vectors}) > 1:
                raise ValueError
            return vectors
        except Exception:
            raise FrontierEmbeddingUnavailable("EmbeddingFailed") from None


def validate_vector(value):
    if not isinstance(value, list) or not value or len(value) > 16384:
        raise ValueError("invalid vector")
    if any(
        isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
        for v in value
    ):
        raise ValueError("invalid vector")
    norm = math.sqrt(sum(v * v for v in value))
    if not norm:
        raise ValueError("zero vector")
    return [float(v / norm) for v in value]


def record_chunks(record: dict) -> list[dict]:
    if not record["eligibility"]["browse"]:
        return []
    # Leads may be found, but never become evidence chunks.
    texts = [
        (
            "overview",
            "\n".join(
                v
                for v in [record["title"], record.get("summary"), record.get("research_question")]
                if v
            ),
        )
    ]
    if record["eligibility"]["rag"]:
        evidence = "\n".join(e["snippet"] for e in record.get("evidence", []) if e.get("snippet"))
        if evidence:
            texts.append(("evidence", evidence))
    return [
        {
            "chunk_id": f"{record['id']}:{kind}",
            "text": text,
            "kind": kind,
            "content_hash": content_hash([kind, text]),
        }
        for kind, text in texts
    ]


class FrontierVectorIndex:
    def __init__(self, store, provider):
        self.store = store
        self.database = store.database
        self.provider = provider

    @property
    def status(self):
        return self.provider.status

    def index_record(self, record_id: str, *, job=None, now=None) -> int:
        started = monotonic()

        def current_time():
            return now + monotonic() - started if now is not None else None

        record = self.store.get_record(record_id)
        if not record:
            raise LookupError("record not found")
        chunks = record_chunks(record) if record.get("is_current", True) else []
        # Retraction is effective even with no model configured.
        if not chunks:
            with self.database.session() as session:
                self.store._fence(session, job, current_time())
                session.execute(
                    delete(FrontierVectorRow).where(FrontierVectorRow.record_id == record_id)
                )
            return 0
        if self.status != "ready":
            return 0
        model = self.provider.model
        hashes = {c["content_hash"] for c in chunks}
        with self.database.session() as session:
            cached = {
                r.content_hash: r.vector
                for r in session.scalars(
                    select(FrontierEmbeddingCacheRow).where(
                        FrontierEmbeddingCacheRow.model == model,
                        FrontierEmbeddingCacheRow.schema_version == SCHEMA_VERSION,
                        FrontierEmbeddingCacheRow.content_hash.in_(hashes),
                    )
                )
            }
        missing = [c for c in chunks if c["content_hash"] not in cached]
        # External calls happen with no open DB transaction.
        if missing:
            vectors = self.provider.embed([c["text"] for c in missing])
            if len(vectors) != len(missing):
                raise ValueError("embedding cardinality mismatch")
            cached.update(
                {
                    c["content_hash"]: validate_vector(v)
                    for c, v in zip(missing, vectors, strict=True)
                }
            )
        if len({len(v) for v in cached.values()}) != 1:
            raise ValueError("embedding model dimension changed")
        with self.database.session() as session:
            self.store._fence(session, job, current_time())
            for c in chunks:
                vector = cached[c["content_hash"]]
                session.execute(
                    insert(FrontierEmbeddingCacheRow)
                    .values(
                        model=model,
                        schema_version=SCHEMA_VERSION,
                        content_hash=c["content_hash"],
                        vector=vector,
                    )
                    .on_conflict_do_nothing()
                )
                values = {
                    "chunk_id": c["chunk_id"],
                    "record_id": record_id,
                    "kind": c["kind"],
                    "model": model,
                    "schema_version": SCHEMA_VERSION,
                    "content_hash": c["content_hash"],
                    "vector": vector,
                }
                session.execute(
                    insert(FrontierVectorRow)
                    .values(**values)
                    .on_conflict_do_update(index_elements=["chunk_id"], set_=values)
                )
            session.execute(
                delete(FrontierVectorRow).where(
                    FrontierVectorRow.record_id == record_id,
                    FrontierVectorRow.chunk_id.not_in([c["chunk_id"] for c in chunks]),
                )
            )
        return len(missing)

    def search(self, query: str, limit: int = 20) -> list[dict]:
        if self.status != "ready" or not query.strip():
            return []
        vector = validate_vector(self.provider.embed([query])[0])
        # Current eligibility is checked on every retrieval, so stale vectors cannot leak.
        allowed = {r["id"]: r for r in self.store.list_records() if r["eligibility"]["browse"]}
        with self.database.session() as session:
            rows = list(
                session.scalars(
                    select(FrontierVectorRow).where(
                        FrontierVectorRow.model == self.provider.model,
                        FrontierVectorRow.schema_version == SCHEMA_VERSION,
                    )
                )
            )
        scores = {}
        for row in rows:
            if row.record_id not in allowed or len(row.vector) != len(vector):
                continue
            score = sum(a * b for a, b in zip(vector, row.vector, strict=True))
            scores[row.record_id] = max(scores.get(row.record_id, -1), score)
        return [
            {"record_id": key, "score": score}
            for key, score in sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:limit]
        ]
