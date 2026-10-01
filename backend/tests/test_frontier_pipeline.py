"""Offline worker tests: SQLite plus fake ports, never a live provider or source."""

from copy import deepcopy
from datetime import date
from unittest.mock import Mock

import httpx
import pytest
from sqlalchemy import select

from qunxue_api.adapters.frontier_models import (
    FrontierExtractor,
    FrontierModelConfig,
    FrontierModelOutputError,
    FrontierModelUnavailable,
    FrontierVerifier,
)
from qunxue_api.adapters.frontier_sources import DisabledSourceAdapter
from qunxue_api.adapters.sqlite.base import Base
from qunxue_api.adapters.sqlite.database import Database
from qunxue_api.adapters.sqlite.frontier_models import (
    FrontierIndexRow,
    FrontierJobRow,
    FrontierSnapshotRow,
    FrontierTopicRunRow,
)
from qunxue_api.adapters.sqlite.frontier_repository import SqliteFrontierStore
from qunxue_api.application import frontier_pipeline
from qunxue_api.application.frontier_pipeline import FrontierWorker
from qunxue_api.modules.frontier_knowledge import FrontierService

TEXT = (
    "The survey included 120 respondents and 25% reported greater trust. "
    "The authors describe the sample, the setting, the uncertainty, and the limits of "
    "generalizing the observed association. The result does not demonstrate causation."
)


@pytest.fixture
def store(tmp_path):
    database = Database(f"sqlite:///{tmp_path / 'frontier.db'}")
    Base.metadata.create_all(
        database.engine,
        tables=[
            table for name, table in Base.metadata.tables.items() if name.startswith("frontier_")
        ],
    )
    store = SqliteFrontierStore(database)
    store.import_seed({
        "generated_at": "2026-10-01",
        "records": [{
            "id": "study-1",
            "title": "Trust study",
            "source_name": "社会学研究",
            "url": "https://sociology.nju.edu.cn/study",
            "material_type": "research_abstract",
            "verification_status": "lead_only",
            "verification_note": "Manually inspected public abstract, not full text.",
            "summary": "Public research lead",
            "topics": ["社会信任"],
            "authors": ["Example author"],
            "findings": [],
            "evidence": [{
                "url": "https://sociology.nju.edu.cn/study",
                "locator": "Abstract",
                "snippet": TEXT,
                "supports": ["findings"],
            }],
        }],
    })
    yield store
    database.engine.dispose()


@pytest.fixture(autouse=True)
def frozen_clock(monkeypatch):
    monkeypatch.setattr(frontier_pipeline, "monotonic", lambda: 0.0)
    monkeypatch.setattr(frontier_pipeline, "time", lambda: 1_800_000_000.0)

    def reject_network(*_args, **_kwargs):
        raise AssertionError("Live HTTP is forbidden in offline worker tests")

    monkeypatch.setattr(httpx.Client, "send", reject_network)


def snapshot_id(store):
    return store.get_record("study-1")["snapshot_id"]


def change_snapshot(store, **changes):
    with store.database.session() as session:
        row = session.get(FrontierSnapshotRow, snapshot_id(store))
        row.payload = {**row.payload, **deepcopy(changes)}


def extraction(store, **changes):
    block = store.get_snapshot(snapshot_id(store))["blocks"][0]
    return {
        "research_question": "How do respondents describe trust?",
        "methods": ["Survey"],
        "data": "Survey responses",
        "sample": "120 respondents",
        "findings": [{
            "claim_text": "25% reported greater trust.",
            "evidence_block_ids": [block["block_id"]],
        }],
        "missing_reasons": {},
        **changes,
    }


def worker(store, *, extractor=None, verifier=None, sources=None, topic_service=None):
    extractor = extractor if extractor is not None else Mock()
    verifier = verifier if verifier is not None else Mock()
    return FrontierWorker(
        store, extractor, verifier, sources or {}, topic_service or FrontierService(store),
    )


def enqueue(store, stage, *, payload=None, object_id=None):
    return store.enqueue(stage, object_id or snapshot_id(store), f"test-{stage}", payload)


def job_result(store, job_id):
    return next(job for job in store.list_jobs() if job["job_id"] == job_id)


def supported():
    return {"status": "supported", "reason": "The cited evidence supports the complete claim."}


def test_empty_worker_and_construction_do_not_call_external_ports(store):
    extractor, verifier = Mock(), Mock()
    runner = worker(store, extractor=extractor, verifier=verifier)
    assert runner.run_once(now=100) is False
    extractor.extract.assert_not_called()
    verifier.verify.assert_not_called()


def test_parse_extract_verify_are_separate_leased_jobs_and_not_publication(store):
    change_snapshot(store, scope="full_text", source_verified=True)
    original = store.get_record("study-1")
    original_snapshot = store.get_snapshot(snapshot_id(store))
    extractor = Mock()
    extractor.extract.return_value = extraction(store)
    verifier = Mock()
    verifier.verify.return_value = supported()
    runner = worker(store, extractor=extractor, verifier=verifier)
    parse_id = enqueue(store, "PARSE")

    assert runner.run_once(now=100) is True
    assert job_result(store, parse_id)["status"] == "completed"
    assert {j["stage"] for j in store.list_jobs()} == {"PARSE", "EXTRACT"}
    extractor.extract.assert_not_called()

    assert runner.run_once(now=101) is True
    extractor.extract.assert_called_once_with({
        "scope": "full_text",
        "blocks": [{key: block[key] for key in ("block_id", "text", "locator")}
                   for block in original_snapshot["blocks"]],
    })
    verifier.verify.assert_not_called()
    assert {j["stage"] for j in store.list_jobs()} == {"PARSE", "EXTRACT", "VERIFY"}
    with store.database.session() as session:
        verify = session.scalar(select(FrontierJobRow).where(FrontierJobRow.stage == "VERIFY"))
        assert verify.object_id == snapshot_id(store)
        assert verify.payload == {"extracted": extraction(store)}

    assert runner.run_once(now=102) is True
    assert runner.run_once(now=103) is False
    assert len(store.list_reviews()) == 1
    assert store.list_reviews()[0]["verification_status"] == "verified_frontier"
    assert store.list_reviews()[0]["verdicts"] == [supported()]
    assert store.get_record("study-1") == original
    assert store.get_snapshot(snapshot_id(store)) == original_snapshot


@pytest.mark.parametrize("scope", ["abstract_or_notice_only", "metadata_and_short_excerpt"])
def test_verified_abstract_stays_a_lead_even_with_payload_upgrade_attempt(store, scope):
    change_snapshot(store, scope=scope, source_verified=True)
    verifier = Mock()
    verifier.verify.return_value = supported()
    enqueue(store, "VERIFY", payload={
        "extracted": extraction(store), "scope": "full_text", "source_verified": True,
        "material_type": "research_full_text",
    })
    worker(store, verifier=verifier).run_once(now=100)
    assert store.list_reviews()[0]["verification_status"] == "lead_only"


@pytest.mark.parametrize("verified", [None, False, "true", 1])
def test_source_identity_must_be_verified_in_snapshot_not_job_payload(store, verified):
    change_snapshot(store, scope="full_text", source_verified=verified)
    verifier = Mock()
    verifier.verify.return_value = supported()
    enqueue(store, "VERIFY", payload={"extracted": extraction(store), "source_verified": True})
    worker(store, verifier=verifier).run_once(now=100)
    result = store.list_reviews()[0]
    assert result["verification_status"] == "review_queue"
    assert result["error"] == "EvidenceNotQualified"


@pytest.mark.parametrize("status", ["partially_supported", "unsupported"])
def test_insufficient_verification_is_queued_for_review(store, status):
    change_snapshot(store, scope="full_text", source_verified=True)
    verifier = Mock()
    verifier.verify.return_value = {"status": status, "reason": "The claim is not fully evidenced."}
    job_id = enqueue(store, "VERIFY", payload={"extracted": extraction(store)})
    worker(store, verifier=verifier).run_once(now=100)
    assert job_result(store, job_id)["status"] == "completed"
    assert store.list_reviews()[0]["verification_status"] == "review_queue"


def test_supported_model_verdict_cannot_override_numeric_evidence_gate(store):
    change_snapshot(store, scope="full_text", source_verified=True)
    extracted = extraction(store)
    extracted["findings"][0]["claim_text"] = "99% reported greater trust."
    verifier = Mock()
    verifier.verify.return_value = supported()
    enqueue(store, "VERIFY", payload={"extracted": extracted})
    worker(store, verifier=verifier).run_once(now=100)
    assert store.list_reviews()[0]["verification_status"] == "review_queue"


def test_verifier_uses_only_each_claims_cited_evidence(store):
    original = store.get_snapshot(snapshot_id(store))["blocks"][0]
    additional = {"block_id": "body-2", "text": "A separate qualitative finding.", "locator": "p2"}
    uncited = {"block_id": "unrelated", "text": "SECRET UNCITED TEXT", "locator": "p3"}
    change_snapshot(store, scope="full_text", blocks=[original, additional, uncited])
    extracted = extraction(store)
    extracted["findings"][0]["evidence_block_ids"].append("body-2")
    extracted["findings"].append({
        "claim_text": "A separate qualitative finding.", "evidence_block_ids": ["body-2"],
    })
    verifier = Mock()
    verifier.verify.return_value = supported()
    enqueue(store, "VERIFY", payload={"extracted": extracted})
    worker(store, verifier=verifier).run_once(now=100)
    assert verifier.verify.call_count == 2
    first_claim, first_evidence = verifier.verify.call_args_list[0].args
    assert first_claim == extracted["findings"][0]["claim_text"]
    assert first_evidence["text"] == TEXT + "\n\n" + additional["text"]
    assert "SECRET" not in first_evidence["text"]
    assert verifier.verify.call_args_list[1].args == (additional["text"], additional)


@pytest.mark.parametrize("stage", ["DISCOVER", "FETCH"])
def test_disabled_sources_are_blocked_with_the_configured_reason(store, stage):
    reason = "WeRSS尚未部署或授权，公众号认证主体尚未核验"
    source = DisabledSourceAdapter("sociology-perspective", reason)
    job_id = enqueue(store, stage, object_id="sociology-perspective", payload={
        "source_id": "sociology-perspective",
    })
    runner = worker(store, sources={"sociology-perspective": source})
    assert runner.run_once(now=100) is True
    result = job_result(store, job_id)
    assert (result["status"], result["error"], result["attempt"]) == ("blocked", reason, 1)
    assert runner.run_once(now=1000) is False


def test_unconfigured_source_and_unpersisted_collection_never_report_success(store):
    first = enqueue(store, "DISCOVER", object_id="missing-source")
    worker(store).run_once(now=100)
    assert job_result(store, first)["error"] == "SourceNotConfigured"
    source = Mock()
    source.discover.return_value = ()
    second = store.enqueue("DISCOVER", "source", "new-source")
    worker(store, sources={"source": source}).run_once(now=101)
    assert job_result(store, second)["status"] == "blocked"
    assert job_result(store, second)["error"] == "SourcePersistenceNotConfigured"


@pytest.mark.parametrize("stage", ["EXTRACT", "VERIFY"])
@pytest.mark.parametrize("configured", [False, True])
def test_actual_model_adapters_are_blocked_without_network_opt_in(store, stage, configured):
    config = FrontierModelConfig(
        base_url="https://provider.invalid/v1" if configured else None,
        api_key="never-transmitted-test-key" if configured else None,
        model="test-model" if configured else None,
        allow_network=False,
    )
    job_id = enqueue(store, stage, payload={"extracted": extraction(store)})
    runner = worker(store, extractor=FrontierExtractor(config), verifier=FrontierVerifier(config))
    runner.run_once(now=100)
    result = job_result(store, job_id)
    assert result["status"] == "blocked"
    assert result["error"] == ("NetworkDisabled" if configured else "NotConfigured")
    assert store.list_reviews() == []
    assert runner.run_once(now=1000) is False


@pytest.mark.parametrize("stage", ["EXTRACT", "VERIFY"])
def test_invalid_model_output_is_reviewed_without_retry_or_raw_response(store, stage):
    extractor, verifier = Mock(), Mock()
    extractor.extract.side_effect = FrontierModelOutputError("InvalidJSON")
    verifier.verify.side_effect = FrontierModelOutputError("InvalidSchema")
    job_id = enqueue(store, stage, payload={"extracted": extraction(store)})
    worker(store, extractor=extractor, verifier=verifier).run_once(now=100)
    result = store.list_reviews()[0]
    assert result["verification_status"] == "review_queue"
    assert result["error"] == ("InvalidJSON" if stage == "EXTRACT" else "InvalidSchema")
    assert job_result(store, job_id)["status"] == "completed"


@pytest.mark.parametrize("blocks", [[], [{}], [{"block_id": "a", "text": "", "locator": "p1"}]])
def test_parse_rejects_unusable_blocks_before_extracting(store, blocks):
    change_snapshot(store, blocks=blocks)
    extractor = Mock()
    job_id = enqueue(store, "PARSE")
    worker(store, extractor=extractor).run_once(now=100)
    extractor.extract.assert_not_called()
    assert len(store.list_jobs()) == 1
    if blocks and isinstance(blocks[0], dict) and blocks[0].get("text") == "":
        assert job_result(store, job_id)["status"] == "blocked"
        assert job_result(store, job_id)["error"] == "AwaitingSourceText"
        return
    assert job_result(store, job_id)["status"] == "completed"
    assert store.list_reviews()[0]["error"] == "InvalidEvidence"


@pytest.mark.parametrize("change", ["duplicate", "scope", "snapshot_id"])
def test_parse_rejects_ambiguous_or_mismatched_snapshot(store, change):
    snapshot = store.get_snapshot(snapshot_id(store))
    changes = {
        "duplicate": {"blocks": snapshot["blocks"] * 2},
        "scope": {"scope": ["full_text"]},
        "snapshot_id": {"snapshot_id": "unrelated-snapshot"},
    }
    change_snapshot(store, **changes[change])
    enqueue(store, "PARSE")
    worker(store).run_once(now=100)
    assert store.list_reviews()[0]["error"] == "InvalidEvidence"


def test_missing_snapshot_is_explicitly_blocked(store):
    job_id = enqueue(store, "PARSE", object_id="snapshot-does-not-exist")
    worker(store).run_once(now=100)
    assert job_result(store, job_id)["status"] == "blocked"
    assert job_result(store, job_id)["error"] == "SnapshotNotFound"
    assert store.list_reviews() == []


@pytest.mark.parametrize("verdict", [None, {}, {"status": [], "reason": "untrusted"},
                                      {"status": "supported", "reason": ""}])
def test_malformed_verifier_result_is_reviewed(store, verdict):
    verifier = Mock()
    verifier.verify.return_value = verdict
    enqueue(store, "VERIFY", payload={"extracted": extraction(store)})
    worker(store, verifier=verifier).run_once(now=100)
    assert store.list_reviews()[0]["error"] == "InvalidEvidence"


@pytest.mark.parametrize("stage", ["EXTRACT", "VERIFY"])
def test_fabricated_evidence_ids_are_never_sent_to_verifier(store, stage):
    extracted = extraction(store)
    extracted["findings"][0]["evidence_block_ids"] = ["invented-block"]
    extractor, verifier = Mock(), Mock()
    extractor.extract.return_value = extracted
    enqueue(store, stage, payload={"extracted": extracted})
    worker(store, extractor=extractor, verifier=verifier).run_once(now=100)
    verifier.verify.assert_not_called()
    assert store.list_reviews()[0]["verification_status"] == "review_queue"


def test_generic_failures_are_redacted_and_stop_after_four_attempts(store):
    extractor = Mock()
    extractor.extract.side_effect = RuntimeError("Bearer PRIVATE-KEY https://secret-provider/body")
    job_id = enqueue(store, "EXTRACT")
    runner = worker(store, extractor=extractor)
    for attempt, now, delay in [(1, 100, 30), (2, 130, 120), (3, 250, 600), (4, 850, 600)]:
        assert runner.run_once(now=now) is True
        result = job_result(store, job_id)
        assert result["attempt"] == attempt
        assert result["error"] == "WorkerFailed"
        assert result["next_run_at"] == now + delay
        assert result["status"] == ("failed" if attempt == 4 else "retry")
        assert runner.run_once(now=now + delay - 1) is False
    assert runner.run_once(now=10_000) is False
    assert extractor.extract.call_count == 4


def test_request_failed_is_retryable_not_configuration_block(store):
    extractor = Mock()
    extractor.extract.side_effect = FrontierModelUnavailable("RequestFailed")
    job_id = enqueue(store, "EXTRACT")
    worker(store, extractor=extractor).run_once(now=100)
    assert job_result(store, job_id)["status"] == "retry"
    assert job_result(store, job_id)["error"] == "RequestFailed"


def test_expired_extraction_cannot_enqueue_or_finish_replacement_lease(store):
    extracted = extraction(store)
    replacement = []

    def extract(_snapshot):
        replacement.append(store.claim_job(now=221))
        return extracted

    extractor = Mock()
    extractor.extract.side_effect = extract
    job_id = enqueue(store, "EXTRACT")
    worker(store, extractor=extractor).run_once(now=100)
    assert replacement[0].job_id == job_id
    result = job_result(store, job_id)
    assert result["status"] == "running"
    assert result["attempt"] == 2
    assert len(store.list_jobs()) == 1
    assert store.list_reviews() == []


def test_enqueue_fence_rechecks_lease_after_worker_guard(store, monkeypatch):
    extractor = Mock()
    extractor.extract.return_value = extraction(store)
    job_id = enqueue(store, "EXTRACT")
    original_enqueue = store.enqueue

    def raced_enqueue(*args, **kwargs):
        assert store.claim_job(now=221).job_id == job_id
        return original_enqueue(*args, **kwargs)

    monkeypatch.setattr(store, "enqueue", raced_enqueue)
    worker(store, extractor=extractor).run_once(now=100)
    assert len(store.list_jobs()) == 1
    assert job_result(store, job_id)["attempt"] == 2
    assert job_result(store, job_id)["status"] == "running"


def test_expired_trend_calculation_cannot_save_results(store):
    topic_service = Mock()

    def topics(**_kwargs):
        store.claim_job(now=221)
        return [{"id": "stale-topic"}]

    topic_service.topics.side_effect = topics
    job_id = enqueue(store, "TREND", object_id="all")
    worker(store, topic_service=topic_service).run_once(now=100)
    assert job_result(store, job_id)["status"] == "running"
    with store.database.session() as session:
        assert list(session.scalars(select(FrontierTopicRunRow))) == []


def test_slow_verification_respects_elapsed_lease_without_replacement(store, monkeypatch):
    elapsed = [0.0]
    monkeypatch.setattr(frontier_pipeline, "monotonic", lambda: elapsed[0])

    def verify(*_args):
        elapsed[0] = 121
        return supported()

    verifier = Mock()
    verifier.verify.side_effect = verify
    job_id = enqueue(store, "VERIFY", payload={"extracted": extraction(store)})
    worker(store, verifier=verifier).run_once(now=100)
    assert store.list_reviews() == []
    assert job_result(store, job_id)["status"] == "running"
    assert store.claim_job(now=221).attempt == 2


def test_verifier_cannot_mutate_source_scope_or_evidence(store):
    original = store.get_snapshot(snapshot_id(store))

    def verify(_claim, block):
        block["text"] = "99% unsupported alteration"
        return supported()

    verifier = Mock()
    verifier.verify.side_effect = verify
    enqueue(store, "VERIFY", payload={"extracted": extraction(store)})
    worker(store, verifier=verifier).run_once(now=100)
    assert store.get_snapshot(snapshot_id(store)) == original
    assert store.list_reviews()[0]["verification_status"] == "lead_only"


def test_external_model_call_holds_no_database_transaction(store):
    def extract(_snapshot):
        # BEGIN IMMEDIATE on a separate connection would fail if a write transaction
        # were held by the worker across the external operation.
        with store.database.engine.connect() as connection:
            connection.exec_driver_sql("PRAGMA busy_timeout=1")
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            connection.exec_driver_sql("ROLLBACK")
        return extraction(store)

    extractor = Mock()
    extractor.extract.side_effect = extract
    job_id = enqueue(store, "EXTRACT")
    worker(store, extractor=extractor).run_once(now=100)
    assert job_result(store, job_id)["status"] == "completed"
    assert any(job["stage"] == "VERIFY" for job in store.list_jobs())


def test_index_and_trend_use_store_and_explicit_as_of_without_model(store):
    extractor, verifier = Mock(), Mock()
    topics = [{"id": "topic-1", "record_ids": ["study-1"]}]
    topic_service = Mock()
    topic_service.topics.return_value = topics
    runner = worker(store, extractor=extractor, verifier=verifier, topic_service=topic_service)
    index_id = enqueue(store, "INDEX", object_id="study-1")
    assert runner.run_once(now=100) is True
    assert job_result(store, index_id)["status"] == "completed"
    with store.database.session() as session:
        assert session.get(FrontierIndexRow, "study-1").embedding_status == "not_configured"
    trend_id = enqueue(store, "TREND", object_id="all", payload={"as_of": "2026-10-01"})
    runner.run_once(now=101)
    assert job_result(store, trend_id)["status"] == "completed"
    topic_service.topics.assert_called_once_with(as_of=date(2026, 10, 1))
    with store.database.session() as session:
        saved = session.scalar(select(FrontierTopicRunRow))
        assert saved.as_of == "2026-10-01"
        assert saved.payload == topics
    extractor.extract.assert_not_called()
    verifier.verify.assert_not_called()


def test_review_save_rechecks_lease_atomically_after_worker_guard(store, monkeypatch):
    verifier = Mock()
    verifier.verify.return_value = supported()
    job_id = enqueue(store, "VERIFY", payload={"extracted": extraction(store)})
    original_save = store.save_review_result

    def raced_save(*args, **kwargs):
        assert store.claim_job(now=221).job_id == job_id
        return original_save(*args, **kwargs)

    monkeypatch.setattr(store, "save_review_result", raced_save)
    worker(store, verifier=verifier).run_once(now=100)
    assert store.list_reviews() == []
    assert job_result(store, job_id)["attempt"] == 2
    assert job_result(store, job_id)["status"] == "running"
