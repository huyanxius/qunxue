import json
import socket
import time
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Any
from uuid import UUID

import pytest

import qunxue_api.adapters.model as model
from qunxue_api.adapters.sqlite import Base
from qunxue_api.adapters.sqlite.database import Database
from qunxue_api.bootstrap import create_app
from qunxue_api.modules.knowledge_catalog import (
    KnowledgeReleaseLevel,
    KnowledgeReleaseRef,
    SourceVerificationStatus,
)
from qunxue_api.modules.research_framework import (
    AuditFindingSeverity,
    AuditFindingType,
    AuditOverallStatus,
    FrameworkVersionSnapshot,
    MethodIntentSnapshot,
    ResearchFrameworkDraft,
    ResearchFrameworkDraftInput,
)
from qunxue_api.modules.research_intake import ConfirmedPhenomenonSnapshot
from qunxue_api.modules.theory_matching import (
    CandidateJudgementRunStatus,
    CandidateOrigin,
    ConfirmedTheoryPlanSnapshot,
    EvidenceBundleSnapshot,
    EvidenceItemSnapshot,
    TheoryCandidateContentSnapshot,
    TheoryCandidateSnapshot,
    TheoryDecisionAction,
    TheoryDecisionRecord,
    TheoryJudgementBatchInput,
    TheoryJudgementBatchItem,
    TheoryJudgementDraft,
    TheoryJudgementInput,
    TheoryJudgementVerdict,
    TheoryUseAssignment,
)
from qunxue_api.settings import Settings

NOW = datetime(2026, 8, 10, 9, 0, tzinfo=UTC)
RELEASE = KnowledgeReleaseRef(
    knowledge_release_id="knowledge-reviewed-v3",
    level=KnowledgeReleaseLevel.FINAL,
    content_hash="sha256:knowledge-reviewed-v3",
)
PHENOMENON = ConfirmedPhenomenonSnapshot(
    task_id=UUID(int=1),
    phenomenon_query_id=UUID(int=2),
    version=1,
    phenomenon="成员流动后社区互助降低",
    research_intent="比较关系网络与资源机制",
    context="去标识化社区访谈摘要",
)
CONTENT = TheoryCandidateContentSnapshot(
    theory_id="theory-social-capital",
    title="社会资本理论",
    origin=CandidateOrigin.REVIEWED_KNOWLEDGE,
    problem_focus="重复互动如何维持互惠规范",
    core_claims=("持续互动有助于形成互惠规范",),
    analysis_levels=("关系网络",),
    source_ids=("source-reviewed-1",),
    reviewed_profile=None,
    formal_adoption_eligible=True,
    adoption_blockers=(),
    knowledge_id="knowledge-social-capital",
)
EVIDENCE = EvidenceItemSnapshot(
    evidence_ref_id="evidence-reviewed-1",
    claim="成员流动削弱重复互动",
    excerpt="去标识化摘要",
    locator="review:1",
    source=None,
    verification_status=SourceVerificationStatus.VERIFIED,
    use_boundary="仅支持本次理论判断",
)
JUDGEMENT_INPUT = TheoryJudgementInput(
    knowledge_release=RELEASE,
    phenomenon=PHENOMENON,
    candidate=CONTENT,
    comparison_candidates=(),
    evidence_items=(EVIDENCE,),
)
PREVIOUS_JUDGEMENT = TheoryJudgementDraft(
    verdict=TheoryJudgementVerdict.CONDITIONAL,
    match_rationale="待更新",
    applicable_conditions=(),
    limitations=(),
    material_requirements=(),
    evidence_gaps=(),
    alternative_explanations=(),
    evidence_ref_ids=(EVIDENCE.evidence_ref_id,),
)
CANDIDATE = TheoryCandidateSnapshot(
    candidate_id=UUID(int=3),
    candidate_version=1,
    content=CONTENT,
    judgement=PREVIOUS_JUDGEMENT,
    trace_id=UUID(int=4),
    request_id=UUID(int=5),
    contract_version="theory-judgement.v1",
)
BUNDLE = EvidenceBundleSnapshot(
    evidence_bundle_id="bundle-reviewed-1",
    version=1,
    content_hash="sha256:bundle-reviewed-1",
    release=RELEASE,
    theory_profiles=(),
    evidence_items=(EVIDENCE,),
)
THEORY_PLAN = ConfirmedTheoryPlanSnapshot(
    theory_plan_id=UUID(int=6),
    task_id=PHENOMENON.task_id,
    match_run_id=UUID(int=7),
    decision_set_id=UUID(int=8),
    version=1,
    phenomenon=PHENOMENON,
    knowledge_release=RELEASE,
    evidence_bundle=BUNDLE,
    candidates=(CANDIDATE,),
    decisions=(
        TheoryDecisionRecord(
            decision_id=UUID(int=9),
            candidate_id=CANDIDATE.candidate_id,
            candidate_version=1,
            action=TheoryDecisionAction.ADOPT,
            reason="用于比较关系网络机制",
            related_source_ids=(),
            revised_applicability=None,
            recorded_at=NOW,
        ),
    ),
    use_assignments=(
        TheoryUseAssignment(
            candidate_id=CANDIDATE.candidate_id,
            role_code="primary",
            responsibility="解释重复互动机制",
        ),
    ),
    relations=(),
    confirmed_at=NOW,
)
FRAMEWORK_INPUT = ResearchFrameworkDraftInput(
    theory_plan=THEORY_PLAN,
    original_research_question="社区互助为什么减少？",
    confirmed_research_question="成员流动如何影响社区互助？",
    question_adjustment_reason="收敛到可观察机制",
    research_object="社区成员",
    analysis_unit="成员关系",
    context=PHENOMENON.context,
    method_intent=MethodIntentSnapshot(
        method_kind=None,
        constraints=("不使用未授权材料",),
        source="user_confirmed",
    ),
)
FRAMEWORK = FrameworkVersionSnapshot(
    framework_id=UUID(int=10),
    task_id=PHENOMENON.task_id,
    version=1,
    input=FRAMEWORK_INPUT,
    draft=ResearchFrameworkDraft(
        concept_mappings=(),
        evidence_requirements=(),
        inference_links=(),
        alternative_explanations=(),
        method_plan=None,
        scope_and_limitations=(),
        unresolved_items=("需要区分竞争解释",),
        next_actions=(),
    ),
    revision_id=UUID(int=11),
)


@dataclass(frozen=True)
class _Reply:
    body: bytes
    status: int = 200
    delay_seconds: float = 0
    disconnect: bool = False
    declared_content_length: int | None = None


class _FakeOpenAIHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        content_length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(content_length)
        self.server.requests.append(  # type: ignore[attr-defined]
            {
                "path": self.path,
                "headers": {key.lower(): value for key, value in self.headers.items()},
                "json": json.loads(body),
            }
        )
        reply = self.server.replies.pop(0)  # type: ignore[attr-defined]
        if reply.delay_seconds:
            time.sleep(reply.delay_seconds)
        if reply.disconnect:
            self.connection.shutdown(socket.SHUT_RDWR)
            self.connection.close()
            return
        self.send_response(reply.status)
        self.send_header("Content-Type", "application/json")
        if reply.declared_content_length is not None:
            self.send_header("Content-Length", str(reply.declared_content_length))
        self.end_headers()
        with suppress(BrokenPipeError):
            self.wfile.write(reply.body)

    def log_message(self, _format: str, *args: object) -> None:
        return


@contextmanager
def _fake_openai_service(*replies: _Reply):
    server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeOpenAIHandler)
    server.daemon_threads = True
    server.replies = list(replies)  # type: ignore[attr-defined]
    server.requests = []  # type: ignore[attr-defined]
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}/v1", server.requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)


def _completion(content: dict[str, Any] | str) -> _Reply:
    serialized_content = content if isinstance(content, str) else json.dumps(content)
    return _Reply(
        body=json.dumps(
            {
                "id": "chatcmpl-local-test",
                "object": "chat.completion",
                "model": "local-sociology-model",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": serialized_content},
                        "finish_reason": "stop",
                    }
                ],
            }
        ).encode()
    )


def _phenomenon_response(phenomenon: str = "成员流动削弱社区重复互动") -> dict[str, Any]:
    return {
        "status": "ok",
        "knowledge_release_id": None,
        "theory_ids": [],
        "output": {
            "phenomenon": phenomenon,
            "research_intent": "比较关系网机制",
            "context": "去标识化社区摘要",
            "source_ref_ids": ["input:direct"],
        },
    }


def _judgement_response() -> dict[str, Any]:
    return {
        "status": "ok",
        "knowledge_release_id": RELEASE.knowledge_release_id,
        "theory_ids": [CONTENT.theory_id],
        "output": {
            "verdict": "conditional",
            "match_rationale": "能解释部分关系机制，仍需比较资源变化。",
            "applicable_conditions": ["存在重复互动"],
            "limitations": ["不能排除资源供给变化"],
            "material_requirements": ["去标识化互助记录"],
            "evidence_gaps": ["缺少时间顺序材料"],
            "alternative_explanations": ["资源供给变化"],
            "evidence_ref_ids": [EVIDENCE.evidence_ref_id],
            "supporting_evidence_ref_ids": [EVIDENCE.evidence_ref_id],
            "conflicting_evidence_ref_ids": [],
        },
    }


def _framework_response() -> dict[str, Any]:
    candidate_id = str(CANDIDATE.candidate_id)
    return {
        "status": "ok",
        "knowledge_release_id": RELEASE.knowledge_release_id,
        "theory_ids": [CONTENT.theory_id],
        "output": {
            "concept_mappings": [
                {
                    "candidate_id": candidate_id,
                    "theory_concept": "重复互动",
                    "meaning_in_study": "解释互惠规范如何维持",
                    "empirical_indicators": ["互助频率"],
                    "unresolved_questions": ["如何区分资源变化"],
                }
            ],
            "evidence_requirements": [
                {
                    "requirement_id": "requirement-1",
                    "related_candidate_ids": [candidate_id],
                    "purpose": "检验重复互动机制",
                    "required_material": "去标识化互助记录",
                    "supporting_signal": "互动越持续互助越稳定",
                    "excluding_signal": "互助与互动持续性无关",
                    "distinguishing_signal": "控制资源变化后仍可观察",
                    "current_gap": "缺少时间序列",
                }
            ],
            "inference_links": [
                {
                    "from_ref": "requirement-1",
                    "to_ref": candidate_id,
                    "relation": "tests",
                    "rationale": "材料用于检验机制",
                    "unresolved": True,
                }
            ],
            "alternative_explanations": ["资源供给变化"],
            "method_plan": None,
            "scope_and_limitations": ["仅适用于当前社区摘要"],
            "unresolved_items": ["需要补充时间序列"],
            "next_actions": ["补充去标识化材料"],
            "ethical_boundaries": ["不上传未授权原始材料"],
        },
    }


def _audit_response() -> dict[str, Any]:
    return {
        "status": "ok",
        "knowledge_release_id": RELEASE.knowledge_release_id,
        "theory_ids": [CONTENT.theory_id],
        "output": {
            "overall_status": "revise",
            "findings": [
                {
                    "summary": "缺少区分性材料",
                    "reason": "尚未区分资源变化",
                    "impact": "无法确认机制",
                    "recommendation": "补充时间序列",
                    "blocking": True,
                    "finding_type": "evidence",
                    "severity": "blocking",
                }
            ],
        },
    }


def test_openai_compatible_provider_is_a_replaceable_model_adapter() -> None:
    provider_type = getattr(model, "OpenAICompatibleModelProvider", None)

    assert provider_type is not None
    provider = provider_type(
        base_url="http://127.0.0.1:9/v1",
        api_key=None,
        model="local-sociology-model",
        timeout_seconds=1,
        capability_tier="base",
    )

    assert provider.descriptor == model.ModelProviderDescriptor(
        provider="openai-compatible",
        model_version="local-sociology-model",
        capability_tier="base",
        demonstration=False,
    )


def test_one_provider_maps_four_capabilities_over_real_local_http() -> None:
    replies = tuple(
        _completion(content)
        for content in (
            _phenomenon_response(),
            _judgement_response(),
            _framework_response(),
            _audit_response(),
        )
    )
    with _fake_openai_service(*replies) as (base_url, requests):
        provider = model.OpenAICompatibleModelProvider(
            base_url=base_url,
            api_key="local-test-key",
            model="local-sociology-model",
            timeout_seconds=1,
            capability_tier="base",
            extra_headers={"X-Tenant": "local-test-tenant"},
        )

        phenomenon = provider.extract_phenomenon(
            raw_input=PHENOMENON.phenomenon,
            research_intent=PHENOMENON.research_intent,
            context=PHENOMENON.context,
        )
        judgement = provider.judge_candidate(input=JUDGEMENT_INPUT)
        framework = provider.draft_framework(input=FRAMEWORK_INPUT)
        audit = provider.audit_framework(framework=FRAMEWORK)

    assert phenomenon.output.phenomenon == "成员流动削弱社区重复互动"
    assert judgement.output.verdict is TheoryJudgementVerdict.CONDITIONAL
    assert judgement.output.evidence_ref_ids == (EVIDENCE.evidence_ref_id,)
    assert judgement.output.supporting_evidence_ref_ids == (EVIDENCE.evidence_ref_id,)
    assert judgement.output.conflicting_evidence_ref_ids == ()
    assert framework.output.concept_mappings[0].candidate_id == CANDIDATE.candidate_id
    assert audit.output.overall_status is AuditOverallStatus.REVISE
    assert audit.output.findings[0].finding_type is AuditFindingType.EVIDENCE
    assert audit.output.findings[0].severity is AuditFindingSeverity.BLOCKING
    assert phenomenon.knowledge_release_id is None
    assert judgement.knowledge_release_id == RELEASE.knowledge_release_id
    assert framework.knowledge_release_id == RELEASE.knowledge_release_id
    assert audit.knowledge_release_id == RELEASE.knowledge_release_id

    assert [request["path"] for request in requests] == ["/v1/chat/completions"] * 4
    assert all(
        request["headers"]["authorization"] == "Bearer local-test-key"
        and request["headers"]["x-tenant"] == "local-test-tenant"
        and request["json"]["model"] == "local-sociology-model"
        and request["json"]["response_format"] == {"type": "json_object"}
        for request in requests
    )
    user_payloads = [
        json.loads(request["json"]["messages"][1]["content"])
        for request in requests
    ]
    assert [payload["capability"] for payload in user_payloads] == [
        "phenomenon_extraction",
        "candidate_judgement_and_rerank",
        "framework_draft",
        "framework_audit",
    ]
    assert user_payloads[1]["allowed_references"] == {
        "knowledge_release_ids": [RELEASE.knowledge_release_id],
        "theory_ids": [CONTENT.theory_id],
        "evidence_ref_ids": [EVIDENCE.evidence_ref_id],
        "candidate_ids": [],
    }
    assert set(
        user_payloads[1]["response_contract"]["success"]["properties"]
    ) == {"status", "knowledge_release_id", "theory_ids", "output"}


def test_only_configuration_switches_between_two_compatible_endpoints() -> None:
    with (
        _fake_openai_service(_completion(_phenomenon_response("endpoint-a"))) as first,
        _fake_openai_service(_completion(_phenomenon_response("endpoint-b"))) as second,
    ):
        first_url, first_requests = first
        second_url, second_requests = second
        first_provider = model.OpenAICompatibleModelProvider(
            base_url=first_url,
            api_key=None,
            model="model-a",
            timeout_seconds=1,
            capability_tier="base",
        )
        second_provider = model.OpenAICompatibleModelProvider(
            base_url=second_url,
            api_key=None,
            model="model-b",
            timeout_seconds=1,
            capability_tier="base",
        )

        first_result = first_provider.extract_phenomenon(
            raw_input="same input", research_intent=None, context=None
        )
        second_result = second_provider.extract_phenomenon(
            raw_input="same input", research_intent=None, context=None
        )

    assert first_result.output.phenomenon == "endpoint-a"
    assert second_result.output.phenomenon == "endpoint-b"
    assert first_requests[0]["json"]["model"] == "model-a"
    assert second_requests[0]["json"]["model"] == "model-b"


def test_sft_uses_the_same_provider_with_a_controlled_resource_header() -> None:
    with _fake_openai_service(_completion(_phenomenon_response())) as (base_url, requests):
        provider = model.OpenAICompatibleModelProvider(
            base_url=base_url,
            api_key=None,
            model="fine-tuned-model",
            timeout_seconds=1,
            capability_tier="sft",
            extra_headers={"X-LoRA-ID": "local-lora-test-id"},
        )

        provider.extract_phenomenon(
            raw_input="same input", research_intent=None, context=None
        )

    assert provider.descriptor.capability_tier == "sft"
    assert requests[0]["headers"]["x-lora-id"] == "local-lora-test-id"


def test_environment_configuration_switches_bootstrap_between_base_and_sft(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    with (
        _fake_openai_service(_completion(_phenomenon_response("base-endpoint"))) as first,
        _fake_openai_service(_completion(_phenomenon_response("sft-endpoint"))) as second,
    ):
        first_url, first_requests = first
        second_url, second_requests = second
        monkeypatch.setenv("QUNXUE_RUNTIME_MODE", "base")
        monkeypatch.setenv("QUNXUE_MODEL_BASE_URL", first_url)
        monkeypatch.setenv("QUNXUE_MODEL_NAME", "base-model")
        monkeypatch.setenv("QUNXUE_MODEL_API_KEY", "local-bootstrap-test-key")
        base_settings = Settings(
            _env_file=None,
            database_url=f"sqlite:///{tmp_path / 'base.db'}",
        )
        base_database = Database(base_settings.database_url)
        Base.metadata.create_all(base_database.engine)
        base_app = create_app(
            settings=base_settings,
            database=base_database,
            knowledge_retriever=object(),
        )

        base_result = base_app.state.model_gateway.build(
            task_id=UUID(int=20),
            raw_input="same input",
            research_intent=None,
            context=None,
        )

        monkeypatch.setenv("QUNXUE_RUNTIME_MODE", "sft")
        monkeypatch.setenv("QUNXUE_MODEL_BASE_URL", second_url)
        monkeypatch.setenv("QUNXUE_MODEL_NAME", "sft-model")
        monkeypatch.setenv("QUNXUE_MODEL_SFT_RESOURCE_ID", "local-lora-test-id")
        sft_settings = Settings(
            _env_file=None,
            database_url=f"sqlite:///{tmp_path / 'sft.db'}",
        )
        sft_database = Database(sft_settings.database_url)
        Base.metadata.create_all(sft_database.engine)
        sft_app = create_app(
            settings=sft_settings,
            database=sft_database,
            knowledge_retriever=object(),
        )

        sft_result = sft_app.state.model_gateway.build(
            task_id=UUID(int=21),
            raw_input="same input",
            research_intent=None,
            context=None,
        )

    base_database.engine.dispose()
    sft_database.engine.dispose()
    assert base_result.phenomenon == "base-endpoint"
    assert sft_result.phenomenon == "sft-endpoint"
    assert base_app.state.model_gateway.descriptor.capability_tier == "base"
    assert sft_app.state.model_gateway.descriptor.capability_tier == "sft"
    assert first_requests[0]["headers"]["authorization"] == (
        "Bearer local-bootstrap-test-key"
    )
    assert "x-lora-id" not in first_requests[0]["headers"]
    assert second_requests[0]["headers"]["x-lora-id"] == "local-lora-test-id"


@pytest.mark.parametrize(
    ("response", "expected_code", "expected_scenario"),
    [
        (_Reply(body=b"{}", status=429), "model_rate_limited", "rate_limited"),
        (_Reply(body=b"not-json"), "model_invalid_output", "invalid_output"),
        (
            _Reply(body=json.dumps({"choices": [None]}).encode()),
            "model_invalid_output",
            "invalid_output",
        ),
        (_completion("not-json"), "model_invalid_output", "invalid_output"),
    ],
)
def test_http_and_json_failures_map_to_sanitized_provider_failures(
    response: _Reply,
    expected_code: str,
    expected_scenario: str,
) -> None:
    with _fake_openai_service(response) as (base_url, _requests):
        provider = model.OpenAICompatibleModelProvider(
            base_url=base_url,
            api_key="never-expose-this-test-key",
            model="local-sociology-model",
            timeout_seconds=1,
            capability_tier="base",
        )

        with pytest.raises(model.ModelProviderFailure) as raised:
            provider.extract_phenomenon(
                raw_input="same input", research_intent=None, context=None
            )

    assert raised.value.code == expected_code
    assert raised.value.scenario.value == expected_scenario
    assert "never-expose-this-test-key" not in str(raised.value)
    assert "not-json" not in str(raised.value)


def test_timeout_and_connection_failure_are_recoverable_without_leaking_config() -> None:
    with _fake_openai_service(
        _Reply(body=_completion(_phenomenon_response()).body, delay_seconds=0.05)
    ) as (base_url, _requests):
        timeout_provider = model.OpenAICompatibleModelProvider(
            base_url=base_url,
            api_key="never-expose-this-test-key",
            model="local-sociology-model",
            timeout_seconds=0.01,
            capability_tier="base",
        )
        with pytest.raises(model.ModelProviderFailure) as timeout:
            timeout_provider.extract_phenomenon(
                raw_input="same input", research_intent=None, context=None
            )

    unused_socket = socket.socket()
    unused_socket.bind(("127.0.0.1", 0))
    host, port = unused_socket.getsockname()
    unused_socket.close()
    unavailable_provider = model.OpenAICompatibleModelProvider(
        base_url=f"http://{host}:{port}/v1",
        api_key="never-expose-this-test-key",
        model="local-sociology-model",
        timeout_seconds=0.1,
        capability_tier="base",
    )
    with pytest.raises(model.ModelProviderFailure) as unavailable:
        unavailable_provider.extract_phenomenon(
            raw_input="same input", research_intent=None, context=None
        )

    assert timeout.value.code == "model_timeout"
    assert timeout.value.scenario.value == "timeout"
    assert unavailable.value.code == "model_unavailable"
    assert unavailable.value.scenario.value == "provider_unavailable"
    assert "never-expose-this-test-key" not in str(timeout.value)
    assert "never-expose-this-test-key" not in str(unavailable.value)


def test_api_key_header_injection_is_rejected_without_echoing_the_value() -> None:
    injected_key = "secret-test-key\r\nInjected: yes"

    with pytest.raises(ValueError) as raised:
        model.OpenAICompatibleModelProvider(
            base_url="http://127.0.0.1:9/v1",
            api_key=injected_key,
            model="local-sociology-model",
            timeout_seconds=1,
            capability_tier="base",
        )

    assert injected_key not in str(raised.value)


@pytest.mark.parametrize(
    "reply",
    [
        _Reply(body=b"", disconnect=True),
        _Reply(body=b"{}", declared_content_length=20),
    ],
    ids=["disconnect", "truncated-response"],
)
def test_interrupted_http_response_is_recorded_as_provider_unavailable(
    reply: _Reply,
) -> None:
    with _fake_openai_service(reply) as (base_url, _requests):
        provider = model.OpenAICompatibleModelProvider(
            base_url=base_url,
            api_key="never-persist-this-test-key",
            model="local-sociology-model",
            timeout_seconds=1,
            capability_tier="base",
        )
        recorder = model.InMemoryModelInvocationRecorder()
        gateway = model.ModelGateway(
            provider=provider,
            recorder=recorder,
            contract_version="model-provider.v1",
        )

        with pytest.raises(model.ModelInvocationError) as raised:
            gateway.build(
                task_id=UUID(int=30),
                raw_input="same input",
                research_intent=None,
                context=None,
            )

    assert raised.value.code == "model_unavailable"
    record = recorder.list_all()[0]
    assert record.error_code == "model_unavailable"
    assert record.output is None
    assert "never-persist-this-test-key" not in record.degradation_reason


@pytest.mark.parametrize(
    "mutate",
    [
        lambda response: response["output"].update(verdict="invented"),
        lambda response: response["output"].update(
            evidence_ref_ids=["evidence-outside-input"]
        ),
        lambda response: response["output"].update(
            supporting_evidence_ref_ids=["evidence-outside-input"]
        ),
        lambda response: response["output"].update(
            conflicting_evidence_ref_ids=["evidence-outside-input"]
        ),
        lambda response: response.update(theory_ids=["theory-outside-input"]),
        lambda response: response.update(knowledge_release_id="release-outside-input"),
    ],
    ids=[
        "invalid-enum",
        "unknown-evidence",
        "unknown-supporting-evidence",
        "unknown-conflicting-evidence",
        "unknown-theory",
        "unknown-release",
    ],
)
def test_invalid_or_out_of_closed_set_judgement_is_rejected_and_not_returned(
    mutate,
) -> None:
    response = _judgement_response()
    mutate(response)
    with _fake_openai_service(_completion(response)) as (base_url, _requests):
        provider = model.OpenAICompatibleModelProvider(
            base_url=base_url,
            api_key=None,
            model="local-sociology-model",
            timeout_seconds=1,
            capability_tier="base",
        )

        with pytest.raises(model.ModelProviderFailure) as raised:
            provider.judge_candidate(input=JUDGEMENT_INPUT)

    assert raised.value.code == "model_invalid_output"
    assert raised.value.knowledge_release_id == RELEASE.knowledge_release_id


def test_framework_candidate_reference_outside_the_input_is_rejected() -> None:
    response = _framework_response()
    response["output"]["concept_mappings"][0]["candidate_id"] = str(UUID(int=999))
    with _fake_openai_service(_completion(response)) as (base_url, _requests):
        provider = model.OpenAICompatibleModelProvider(
            base_url=base_url,
            api_key=None,
            model="local-sociology-model",
            timeout_seconds=1,
            capability_tier="base",
        )

        with pytest.raises(model.ModelProviderFailure) as raised:
            provider.draft_framework(input=FRAMEWORK_INPUT)

    assert raised.value.code == "model_invalid_output"


def test_source_insufficiency_preserves_the_input_release_in_the_failure() -> None:
    response = {
        "status": "insufficient_sources",
        "knowledge_release_id": RELEASE.knowledge_release_id,
        "theory_ids": [CONTENT.theory_id],
    }
    with _fake_openai_service(_completion(response)) as (base_url, _requests):
        provider = model.OpenAICompatibleModelProvider(
            base_url=base_url,
            api_key=None,
            model="local-sociology-model",
            timeout_seconds=1,
            capability_tier="base",
        )

        with pytest.raises(model.ModelProviderFailure) as raised:
            provider.judge_candidate(input=JUDGEMENT_INPUT)

    assert raised.value.code == "insufficient_sources"
    assert raised.value.knowledge_release_id == RELEASE.knowledge_release_id


@pytest.mark.parametrize(
    ("reply", "expected_code"),
    [
        (_Reply(body=b"{}", status=429), "model_rate_limited"),
        (
            _completion(
                {
                    **_judgement_response(),
                    "theory_ids": ["theory-outside-input"],
                }
            ),
            "model_invalid_output",
        ),
    ],
)
def test_gateway_records_http_failures_with_input_release_and_retry_state(
    reply: _Reply,
    expected_code: str,
) -> None:
    with _fake_openai_service(reply) as (base_url, _requests):
        provider = model.OpenAICompatibleModelProvider(
            base_url=base_url,
            api_key="never-persist-this-test-key",
            model="local-sociology-model",
            timeout_seconds=1,
            capability_tier="base",
        )
        recorder = model.InMemoryModelInvocationRecorder()
        gateway = model.ModelGateway(
            provider=provider,
            recorder=recorder,
            contract_version="model-provider.v1",
        )

        result = gateway.judge_and_rerank(
            input=TheoryJudgementBatchInput(
                items=(
                    TheoryJudgementBatchItem(
                        candidate_id=CANDIDATE.candidate_id,
                        candidate_version=1,
                        judgement_input=JUDGEMENT_INPUT,
                    ),
                ),
                target_candidate_ids=(CANDIDATE.candidate_id,),
            )
        )

    assert result.results[0].status is CandidateJudgementRunStatus.FAILED
    assert result.results[0].failure_code == expected_code
    assert result.retryable_candidate_ids == (CANDIDATE.candidate_id,)
    record = recorder.list_all()[0]
    assert record.knowledge_release_id == RELEASE.knowledge_release_id
    assert record.error_code == expected_code
    assert record.output is None
    assert "never-persist-this-test-key" not in record.degradation_reason


@pytest.mark.parametrize(
    "headers",
    [
        {"Authorization": "replacement"},
        {"X-Bad\r\nInjected": "value"},
        {"X-Header": "value\r\nInjected: yes"},
    ],
)
def test_extension_headers_cannot_override_transport_security(headers: dict[str, str]) -> None:
    with pytest.raises(ValueError, match="header"):
        model.OpenAICompatibleModelProvider(
            base_url="http://127.0.0.1:9/v1",
            api_key="local-test-key",
            model="local-sociology-model",
            timeout_seconds=1,
            capability_tier="base",
            extra_headers=headers,
        )
