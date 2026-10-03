# ruff: noqa: F811
from contextlib import contextmanager
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import text, update
from sqlalchemy.orm import Session
from test_durable_billing import wallet  # noqa: F401

from qunxue_api.adapters.model.metering import OperationScope, current_operation
from qunxue_api.adapters.research_agent.course_organization import (
    CourseOrganizationWorker,
    CourseWorkCancelled,
)
from qunxue_api.adapters.sqlite.shared_knowledge import (
    SharedDocumentRow,
    SharedKnowledgeBaseRow,
    SharedKnowledgeDocumentRow,
)
from qunxue_api.modules.billing import BillingContextMissing


@pytest.mark.parametrize("lose_lease", [False, True, "unconfigured"])
def test_course_final_job_fence_prevents_charging_undelivered_job(wallet, lose_lease):
    runtime, engine = wallet
    # Only independent course tables; no catalog import or external model service.
    with engine.begin() as c:
        c.execute(text("CREATE TABLE users(user_id TEXT PRIMARY KEY)"))
    for table in [
        SharedKnowledgeBaseRow.__table__,
        SharedDocumentRow.__table__,
        SharedKnowledgeDocumentRow.__table__,
    ]:
        table.create(engine)

    @contextmanager
    def session():
        with Session(engine, expire_on_commit=False) as s:
            try:
                yield s
                s.commit()
            except BaseException:
                s.rollback()
                raise

    owner, document_id, kb_id = map(str, [uuid4(), uuid4(), uuid4()])
    now = datetime.now(UTC)
    with session() as s:
        s.execute(text("INSERT INTO users VALUES (:owner)"), {"owner": owner})
        s.add(
            SharedKnowledgeBaseRow(
                id=kb_id,
                owner_user_id=owner,
                request_key="synthetic",
                name="synthetic",
                description="",
                share_token=str(uuid4()),
                created_at=now,
                updated_at=now,
            )
        )
        s.add(
            SharedDocumentRow(
                id=document_id,
                owner_user_id=owner,
                request_key="synthetic",
                filename="synthetic.txt",
                media_type="text/plain",
                content_hash="synthetic",
                content=b"synthetic",
                size_bytes=9,
                parse_id=str(uuid4()),
                status="ready",
                segments=[{"segment_id": "s0", "text": "synthetic"}],
                created_at=now,
            )
        )
        s.flush()
        s.add(SharedKnowledgeDocumentRow(knowledge_base_id=kb_id, document_id=document_id))

    class Database:
        pass

    db = Database()
    db.session = session

    class Billing:
        def open(self, **kwargs):
            if lose_lease == "unconfigured":
                raise BillingContextMissing("synthetic missing policy")
            assert kwargs["phase"] == "course_knowledge"
            return OperationScope(
                runtime, user_id="user", run_id=kwargs["run_id"], fingerprint="synthetic"
            )

    def generate(document):
        scope = current_operation(required=True)
        attempt = scope.before_attempt_payload(
            {"model": "gpt-6-luna", "messages": [], "max_tokens": 100},
            provider_host="synthetic.test",
        )
        scope.complete(
            attempt,
            {
                "id": "course-synthetic",
                "model": "gpt-6-luna",
                "usage": {
                    "prompt_tokens": 1000,
                    "completion_tokens": 100,
                    "prompt_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0},
                },
                "choices": [],
            },
            outcome="success",
        )
        if lose_lease:
            with session() as s:
                s.execute(
                    update(SharedDocumentRow)
                    .where(SharedDocumentRow.id == document_id)
                    .values(job_token=str(uuid4()))
                )
        return {
            "summary": "synthetic",
            "topics": [{"title": "synthetic", "summary": "synthetic", "segment_ids": ["s0"]}],
            "relations": [],
        }

    worker = CourseOrganizationWorker(db, generate=generate, billing=Billing())
    if lose_lease is True:
        with pytest.raises(CourseWorkCancelled):
            worker.run_once()
    else:
        assert worker.run_once()
    with engine.connect() as c:
        assert c.scalar(text("SELECT balance FROM credit_accounts")) == (
            10000 if lose_lease else 9999
        )
        if lose_lease == "unconfigured":
            assert c.scalar(text("SELECT count(*) FROM billing_operations")) == 0
            assert c.scalar(text("SELECT knowledge_status FROM shared_documents")) == "failed"
            assert c.scalar(text("SELECT job_token FROM shared_documents")) is None
            return
        assert c.scalar(text("SELECT status FROM billing_operations")) == (
            "error" if lose_lease else "success"
        )
        assert c.scalar(text("SELECT reference_cost_pico FROM billing_attempts")) == 150000000
