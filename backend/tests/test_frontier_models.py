import json
import traceback
from copy import deepcopy

import httpx
import pytest

from qunxue_api.adapters.frontier_models import (
    FrontierExtractor,
    FrontierModelConfig,
    FrontierModelOutputError,
    FrontierModelUnavailable,
    FrontierVerifier,
)
from qunxue_api.modules.frontier_knowledge import qualify_record

SNAPSHOT = {
    "scope": "abstract_or_notice_only",
    "blocks": [
        {
            "block_id": "abstract-1",
            "text": "A survey of 120 participants found that 25% reported greater trust.",
            "locator": {"section": "Abstract", "page": 1},
        },
        {
            "block_id": "notice-1",
            "text": "The full text is unavailable. This is a short abstract only.",
            "locator": {"section": "Notice"},
        },
    ],
}


def _config(**changes):
    return FrontierModelConfig(
        **{
            "base_url": "https://frontier.example.test/v1",
            "api_key": "test-frontier-only-credential",
            "model": "frontier-extraction-model",
            "allow_network": True,
            **changes,
        }
    )


def _extraction():
    return {
        "research_question": None,
        "methods": ["Survey"],
        "data": "Participant survey responses",
        "sample": "120 participants",
        "findings": [
            {
                "claim_text": "25% reported greater trust.",
                "evidence_block_ids": ["abstract-1"],
            }
        ],
        "missing_reasons": {
            "research_question": "Not stated in the abstract.",
            "methods": "",
            "data": "",
            "sample": "",
        },
    }


def _response(content, *, finish_reason="stop"):
    return httpx.Response(
        200,
        json={
            "choices": [
                {
                    "finish_reason": finish_reason,
                    "message": {"role": "assistant", "content": content},
                }
            ]
        },
    )


def _transport(payload):
    return httpx.MockTransport(lambda request: _response(json.dumps(payload)))


def _extract(payload):
    return FrontierExtractor(_config(), _transport(payload)).extract(deepcopy(SNAPSHOT))


def _never_called(request):
    pytest.fail("An unconfigured/disabled adapter must not send a request")


@pytest.mark.parametrize("adapter", [FrontierExtractor, FrontierVerifier])
def test_default_disables_network_even_with_an_injected_transport(adapter):
    config = FrontierModelConfig("https://frontier.example.test/v1", "isolated-key", "model")
    assert config.allow_network is False
    instance = adapter(config, httpx.MockTransport(_never_called))
    with pytest.raises(FrontierModelUnavailable, match="NetworkDisabled"):
        if adapter is FrontierExtractor:
            instance.extract(SNAPSHOT)
        else:
            instance.verify("A claim", SNAPSHOT["blocks"][0])


@pytest.mark.parametrize("field", ["api_key", "model", "base_url"])
@pytest.mark.parametrize("value", [None, "", "  "])
def test_missing_explicit_config_does_not_fall_back_to_existing_model_env(
    monkeypatch, field, value
):
    for name in (
        "OPENAI_API_KEY",
        "QUNXUE_MODEL_API_KEY",
        "QUNXUE_MODEL_BASE_URL",
        "QUNXUE_MODEL_NAME",
        "QUNXUE_FRONTIER_API_KEY",
    ):
        monkeypatch.setenv(name, "existing-model-must-not-be-used")
    extractor = FrontierExtractor(_config(**{field: value}), httpx.MockTransport(_never_called))
    with pytest.raises(FrontierModelUnavailable, match="NotConfigured") as exc:
        extractor.extract(SNAPSHOT)
    assert exc.value.code == "NotConfigured"
    assert "existing-model" not in str(exc.value)


def test_credentials_are_not_in_config_repr():
    assert _config().api_key not in repr(_config())


def test_mock_extraction_sends_explicit_auth_and_strict_schema_without_scope_upgrade():
    requests = []
    snapshot = deepcopy(SNAPSHOT)

    def respond(request):
        requests.append(request)
        assert str(request.url) == "https://frontier.example.test/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer test-frontier-only-credential"
        body = json.loads(request.content)
        assert body["model"] == "frontier-extraction-model"
        assert body["stream"] is False
        response_format = body["response_format"]
        assert response_format["type"] == "json_schema"
        assert response_format["json_schema"]["strict"] is True
        schema = response_format["json_schema"]["schema"]
        assert schema["additionalProperties"] is False
        assert set(schema["required"]) == set(_extraction())
        assert schema["properties"]["missing_reasons"]["additionalProperties"] is False
        assert "untrusted" in body["messages"][0]["content"]
        assert json.loads(body["messages"][1]["content"]) == snapshot
        return _response(json.dumps(_extraction()))

    extractor = FrontierExtractor(_config(), httpx.MockTransport(respond))
    assert requests == []  # Constructing an adapter never creates a request.
    result = extractor.extract(snapshot)
    assert len(requests) == 1
    assert result["sample"] == "120 participants"
    assert result["missing_reasons"] == {"research_question": "Not stated in the abstract."}
    assert "scope" not in result and "status" not in result
    assert snapshot == SNAPSHOT


@pytest.mark.parametrize(
    "scope", sorted({"full_text", "abstract_or_notice_only", "metadata_and_short_excerpt"})
)
def test_supported_scopes_remain_unchanged(scope):
    snapshot = {**deepcopy(SNAPSHOT), "scope": scope}

    def respond(request):
        source = json.loads(json.loads(request.content)["messages"][1]["content"])
        assert source["scope"] == scope
        return _response(json.dumps(_extraction()))

    FrontierExtractor(_config(), httpx.MockTransport(respond)).extract(snapshot)
    assert snapshot["scope"] == scope


@pytest.mark.parametrize(
    "content",
    [
        "provider-body-secret malformed JSON",
        '```json\n{"findings": []}\n```',
        '{"findings": [], "findings": []}',
        '{"sample": NaN}',
        "[]",
        "null",
    ],
)
def test_invalid_json_and_wrong_root_are_rejected_without_raw_output(content):
    extractor = FrontierExtractor(
        _config(), httpx.MockTransport(lambda request: _response(content))
    )
    with pytest.raises(FrontierModelOutputError) as exc:
        extractor.extract(SNAPSHOT)
    assert "provider-body-secret" not in str(exc.value)
    assert _config().api_key not in str(exc.value)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda p: p.update(extra="not permitted"),
        lambda p: p.pop("sample"),
        lambda p: p.update(sample=120),
        lambda p: p.update(methods="Survey"),
        lambda p: p.update(methods=[False]),
        lambda p: p.update(findings="not an array"),
        lambda p: p["findings"][0].update(verified=True),
        lambda p: p["findings"][0].update(evidence_block_ids="abstract-1"),
        lambda p: p["missing_reasons"].update(unrequested="unknown field"),
        lambda p: p["missing_reasons"].update(sample=None),
    ],
)
def test_output_schema_is_checked_locally(mutation):
    payload = _extraction()
    mutation(payload)
    with pytest.raises(FrontierModelOutputError, match="InvalidSchema"):
        _extract(payload)


@pytest.mark.parametrize("ids", [[], ["nonexistent"], ["abstract-1", "abstract-1"], [""]])
def test_findings_require_existing_unique_evidence_blocks(ids):
    payload = _extraction()
    payload["findings"][0]["evidence_block_ids"] = ids
    with pytest.raises(FrontierModelOutputError, match="InvalidEvidenceReference"):
        _extract(payload)


def test_number_from_an_uncited_block_is_not_evidence():
    payload = _extraction()
    payload["findings"][0]["evidence_block_ids"] = ["notice-1"]
    with pytest.raises(FrontierModelOutputError, match="UnsupportedNumber"):
        _extract(payload)


@pytest.mark.parametrize("claim", ["26% reported greater trust.", "120% reported trust."])
def test_changed_percentages_are_rejected(claim):
    payload = _extraction()
    payload["findings"][0]["claim_text"] = claim
    with pytest.raises(FrontierModelOutputError, match="UnsupportedNumber"):
        _extract(payload)


@pytest.mark.parametrize(
    "field,value",
    [
        ("sample", "121 participants"),
        ("data", "Responses from 500 surveys"),
        ("methods", ["Survey with 300 respondents"]),
        ("research_question", "Did trust rise 99%?"),
    ],
)
def test_numbers_in_metadata_fields_require_source_text(field, value):
    payload = _extraction()
    payload[field] = value
    with pytest.raises(FrontierModelOutputError, match="UnsupportedNumber"):
        _extract(payload)


def test_numeric_formatting_and_percent_words_are_normalized_conservatively():
    payload = _extraction()
    payload["sample"] = "120.0 participants"
    payload["findings"][0]["claim_text"] = "25 percent reported greater trust."
    assert _extract(payload)["sample"] == "120.0 participants"
    payload["findings"][0]["claim_text"] = "Trust increased 25 percentage points."
    with pytest.raises(FrontierModelOutputError, match="UnsupportedNumber"):
        _extract(payload)


@pytest.mark.parametrize(
    "snapshot",
    [
        {},
        {"scope": "full_text", "blocks": []},
        {"scope": "guessed_full_text", "blocks": SNAPSHOT["blocks"]},
        {"scope": "full_text", "blocks": [{"block_id": "a", "text": "hello"}]},
        {"scope": "full_text", "blocks": [SNAPSHOT["blocks"][0]] * 2},
    ],
)
def test_invalid_snapshot_is_rejected_before_request(snapshot):
    extractor = FrontierExtractor(_config(), httpx.MockTransport(_never_called))
    with pytest.raises(FrontierModelOutputError, match="InvalidEvidence"):
        extractor.extract(snapshot)


@pytest.mark.parametrize("status", ["supported", "partially_supported", "unsupported"])
def test_independent_verifier_returns_only_enum_and_reason(status):
    payload = {"status": status, "reason": "The abstract reports this result."}
    verifier = FrontierVerifier(
        _config(api_key="independent-verifier-credential", model="independent-verifier"),
        _transport(payload),
    )
    assert verifier.verify("25% reported greater trust.", SNAPSHOT["blocks"][0]) == payload


@pytest.mark.parametrize(
    "payload",
    [
        {"status": "verified", "reason": "Unrecognized enum."},
        {"status": "SUPPORTED", "reason": "Wrong casing."},
        {"status": "supported", "reason": ""},
        {"status": "supported", "reason": "A reason", "score": 1},
        {"status": "supported"},
        {"status": True, "reason": "Wrong type."},
    ],
)
def test_verifier_rejects_bad_enum_shape_or_empty_reason(payload):
    verifier = FrontierVerifier(_config(), _transport(payload))
    with pytest.raises(FrontierModelOutputError, match="InvalidSchema"):
        verifier.verify("A claim", SNAPSHOT["blocks"][0])


def test_verifier_cannot_mark_an_unmatched_number_supported():
    verifier = FrontierVerifier(
        _config(), _transport({"status": "supported", "reason": "Model claimed support."})
    )
    with pytest.raises(FrontierModelOutputError, match="UnsupportedNumber"):
        verifier.verify("99% reported greater trust.", SNAPSHOT["blocks"][0])


@pytest.mark.parametrize("status_code", [302, 401, 429, 500])
def test_provider_errors_and_redirects_are_safe_and_not_retried(status_code):
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(
            status_code,
            text="provider-body-secret",
            headers={"Location": "https://different-provider.example.test/steal-auth"},
        )

    extractor = FrontierExtractor(_config(), httpx.MockTransport(respond))
    with pytest.raises(FrontierModelUnavailable, match="RequestFailed") as exc:
        extractor.extract(SNAPSHOT)
    assert len(requests) == 1
    assert "provider-body-secret" not in str(exc.value)


def test_transport_errors_hide_provider_and_credential_details():
    def fail(request):
        raise httpx.ConnectError("provider-body-secret test-frontier-only-credential")

    extractor = FrontierExtractor(_config(), httpx.MockTransport(fail))
    with pytest.raises(FrontierModelUnavailable, match="RequestFailed") as exc:
        extractor.extract(SNAPSHOT)
    formatted = "".join(traceback.format_exception(exc.value))
    assert "provider-body-secret" not in formatted
    assert _config().api_key not in formatted


@pytest.mark.parametrize("finish_reason", ["length", "content_filter", None, "tool_calls"])
def test_truncated_or_nonfinal_model_output_is_rejected(finish_reason):
    extractor = FrontierExtractor(
        _config(),
        httpx.MockTransport(
            lambda request: _response(json.dumps(_extraction()), finish_reason=finish_reason)
        ),
    )
    with pytest.raises(FrontierModelOutputError, match="InvalidResponse"):
        extractor.extract(SNAPSHOT)


@pytest.mark.parametrize(
    "base_url",
    [
        "ftp://frontier.example.test",
        "https://username:password@frontier.example.test/v1",
        "https://frontier.example.test/v1?credential=secret",
        "https://frontier.example.test/v1#fragment",
        "not a URL",
    ],
)
def test_invalid_or_credential_bearing_urls_are_rejected(base_url):
    extractor = FrontierExtractor(_config(base_url=base_url), httpx.MockTransport(_never_called))
    with pytest.raises(FrontierModelUnavailable, match="NotConfigured"):
        extractor.extract(SNAPSHOT)


def _qualify(
    *,
    evidence="A sample of 1,200 respondents reported 25% greater trust.",
    claim="A sample of 1200 respondents reported 25 percent greater trust.",
    scope="full_text",
    extra_block=None,
):
    snapshot = {
        "scope": scope,
        "blocks": [
            {
                "block_id": "body-1",
                "text": evidence + " The study explains the evidence and its limitations." * 5,
            }
        ],
    }
    if extra_block:
        snapshot["blocks"].append(extra_block)
    return qualify_record(
        snapshot,
        [{"claim_text": claim, "evidence_block_ids": ["body-1"]}],
        [{"status": "supported", "reason": "The block supports this claim."}],
        source_verified=True,
        material_type="research_abstract",
    )


def test_domain_gate_accepts_supported_normalized_numeric_quantities():
    assert _qualify() == "verified_frontier"


@pytest.mark.parametrize(
    "evidence,claim",
    [
        ("There were 1200 respondents.", "There were 120 respondents."),
        ("The sample had 25 participants.", "25% showed an increase."),
        ("The result was 25%.", "The increase was 25 percentage points."),
        ("The result was 25%.", "The result was 5%."),
        ("The result was 12.5%.", "The result was 2.5%."),
        ("The result was -25%.", "The result was 25%."),
        ("The result was −25%.", "The result was 25%."),
        ("The result was 25%.", "The result was .5%."),
        ("The sample had 1 respondent.", "The sample had 1 million respondents."),
        ("The sample had 1 respondent.", "The sample had 1万 respondents."),
        ("The sample had 1200 respondents.", "The sample had 1e99999999999999999999999 people."),
    ],
)
def test_domain_gate_rejects_substrings_unit_changes_and_unparseable_numbers(evidence, claim):
    assert _qualify(evidence=evidence, claim=claim) == "review_queue"


def test_domain_gate_cannot_borrow_a_number_from_an_uncited_block():
    assert (
        _qualify(
            evidence="There were 100 respondents.",
            claim="There were 120 respondents.",
            extra_block={"block_id": "uncited", "text": "Another study had 120 respondents."},
        )
        == "review_queue"
    )


@pytest.mark.parametrize(
    "barrier",
    [
        "CAPTCHA challenge",
        "Please verify you are human",
        "Checking your browser",
        "Enable JavaScript and cookies",
        "Access denied",
        "Authentication required",
        "Please log in",
        "Sign in to continue",
        "Subscribe to read",
        "Purchase full text",
        "Access through your institution",
        "请输入验证码",
        "请先登录后阅读",
        '<input type="password" name="account-password">',
    ],
)
def test_domain_gate_rejects_long_login_paywall_and_challenge_pages(barrier):
    assert _qualify(evidence=barrier * 20, claim="The study reports a finding.") == "review_queue"


@pytest.mark.parametrize("scope", ["abstract_or_notice_only", "metadata_and_short_excerpt"])
def test_domain_gate_does_not_upgrade_an_abstract_or_excerpt(scope):
    assert _qualify(scope=scope) == "lead_only"


@pytest.mark.parametrize("claim", [".5% reported trust", "1 million participants reported trust"])
def test_adapter_rejects_unsupported_fractional_percent_and_sample_magnitudes(claim):
    payload = _extraction()
    payload["findings"][0]["claim_text"] = claim
    with pytest.raises(FrontierModelOutputError, match="UnsupportedNumber"):
        _extract(payload)


def test_invalid_scope_type_and_large_exponent_produce_safe_validation_errors():
    extractor = FrontierExtractor(_config(), httpx.MockTransport(_never_called))
    with pytest.raises(FrontierModelOutputError, match="InvalidEvidence"):
        extractor.extract({**SNAPSHOT, "scope": []})
    payload = _extraction()
    payload["sample"] = "1e99999999999999999999999 participants"
    with pytest.raises(FrontierModelOutputError, match="UnsupportedNumber"):
        _extract(payload)
