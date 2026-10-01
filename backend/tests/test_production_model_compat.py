import asyncio
import json

import httpx
import pytest
from pydantic import ValidationError
from pydantic_ai.exceptions import ModelHTTPError

from qunxue_api.adapters.model import OpenAICompatibleModelProvider
from qunxue_api.adapters.research_agent.pydantic_runner import (
    PydanticAIKnowledgeRunner,
    _is_retryable_model_error,
)
from qunxue_api.bootstrap import _model_endpoints_from_settings
from qunxue_api.settings import Settings


def test_fallback_headers_and_store_remain_endpoint_specific():
    settings = Settings(
        _env_file=None,
        model_base_url="https://primary.example.test/v1",
        model_name="primary-model",
        model_api_key="isolated-primary-test-key",
        model_extra_headers={"X-Primary": "isolated-primary-header"},
        model_fallbacks=[
            {
                "base_url": "https://backup.example.test/v1",
                "api_key": "isolated-backup-test-key",
                "extra_headers": {"X-Backup": "isolated-backup-header"},
                "store": False,
            }
        ],
    )
    primary, fallback = _model_endpoints_from_settings(settings)
    assert primary.extra_headers == {"X-Primary": "isolated-primary-header"}
    assert fallback.extra_headers == {"X-Backup": "isolated-backup-header"}
    assert fallback.store is False
    assert "isolated-backup-header" not in repr(settings.model_fallbacks)
    runner = PydanticAIKnowledgeRunner(
        base_url=primary.base_url,
        api_key="isolated-primary-test-key",
        model=primary.model,
        timeout_seconds=30,
        extra_headers=primary.extra_headers,
        fallback_endpoints=((fallback.base_url, "isolated-backup-test-key", fallback.model),),
        fallback_model_settings={
            fallback.endpoint_id: {
                "extra_headers": dict(fallback.extra_headers),
                "openai_store": False,
            }
        },
    )
    backup = runner._agent.model._endpoint_models["fallback-1"]
    assert backup.settings["extra_headers"] == dict(fallback.extra_headers)
    assert backup.settings["openai_store"] is False


def test_deepseek_probe_keeps_one_token_and_disables_reasoning_without_network():
    requests = []

    def reply(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "OK"}}]})

    provider = OpenAICompatibleModelProvider(
        base_url="https://api.deepseek.com",
        api_key="isolated-probe-test-key",
        model="deepseek-flash",
        timeout_seconds=1,
        capability_tier="base",
        store=False,
        probe_transport=httpx.MockTransport(reply),
    )
    asyncio.run(provider.probe())
    assert requests[0]["max_tokens"] == 1
    assert requests[0]["thinking"] == {"type": "disabled"}
    assert requests[0]["store"] is False
    assert "reasoning_effort" not in requests[0]


@pytest.mark.parametrize("status", [401, 402, 403, 404, 429, 503])
def test_production_agent_fallback_classifies_endpoint_failures_as_retryable(status):
    assert _is_retryable_model_error(ModelHTTPError(status_code=status, model_name="isolated"))


@pytest.mark.parametrize(
    "origin",
    [
        "http://example.test",
        "https://user@example.test",
        "https://example.test/path",
        "https://example.test?token=x",
    ],
)
def test_password_recovery_origin_rejects_untrusted_url_shapes(origin):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, password_reset_origin=origin)
