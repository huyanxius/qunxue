"""One metering boundary for every SDK request, including nested calls and retries."""

import hashlib
import json
from contextvars import ContextVar

from qunxue_api.adapters.model.routing import current_model_route_scope
from qunxue_api.adapters.model.token_usage import (
    UnknownTokenUsage,
    UsageSafeOpenAIChatModel,
    UsageSnapshot,
    normalized_usage,
)
from qunxue_api.modules.billing import (
    BillingContextMissing as BillingContextMissing,
)
from qunxue_api.modules.billing import (
    ModelDeliveryRejected as ModelDeliveryRejected,
)

_last_attempt = ContextVar("billing_last_attempt", default=None)


_wire_request = ContextVar("billing_wire_request", default=None)


_current_operation = ContextVar("billing_operation", default=None)


def current_operation(*, required=False):
    scope = _current_operation.get()
    if required and scope is None:
        raise BillingContextMissing("paid invocation has no billing operation")
    return scope


def reject_current_attempt(code):
    scope, prior = current_operation(), _last_attempt.get()
    if scope and prior and prior[0] == scope.run_id:
        scope.runtime.mark_attempt_error(prior[1], code)


def _safe_usage_evidence(raw):
    """Persist only numeric usage facts, never arbitrary provider payloads."""
    from collections.abc import Mapping

    if hasattr(raw, "model_dump"):
        raw = raw.model_dump(exclude_none=True)
    if not isinstance(raw, Mapping):
        return {}
    keys = {
        "input_tokens",
        "output_tokens",
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "cache_creation_input_tokens",
        "cached_tokens",
        "cache_write_tokens",
        "reasoning_tokens",
        "prompt_cache_hit_tokens",
        "prompt_cache_miss_tokens",
    }
    nested = {
        "prompt_tokens_details",
        "input_tokens_details",
        "completion_tokens_details",
        "output_tokens_details",
    }
    return {
        k: v if type(v) is int else _safe_usage_evidence(v)
        for k, v in raw.items()
        if (k in keys and type(v) is int and v >= 0) or (k in nested and isinstance(v, Mapping))
    }


class OperationScope:
    def __init__(self, runtime, *, user_id, run_id, fingerprint, exempt=False,
                 before_network=None, resume=False, settlement_connection=None):
        self.runtime = runtime
        self.run_id = str(run_id)
        self.user_id = str(user_id)
        self.fingerprint = fingerprint
        self.exempt = exempt
        self.before_network = before_network
        self.finished = False
        self.resume = resume
        self.settlement_connection = settlement_connection

    def __enter__(self):
        self.runtime.start(
            user_id=self.user_id,
            run_id=self.run_id,
            fingerprint=self.fingerprint,
            exempt=self.exempt,
            **({"resume": True} if self.resume else {}),
        )
        self.token = _current_operation.set(self)
        self.last_token = _last_attempt.set(None)
        return self

    def finish(self, outcome, *, connection=None):
        if connection is None and outcome in {"success", "paused"} and self.settlement_connection:
            connection = self.settlement_connection()
        settled = self.runtime.finish(
            run_id=self.run_id, outcome=outcome,
            **({"connection": connection} if connection is not None else {}),
        )
        self.finished = True
        if outcome in {"success", "paused"} and settled in {"error", "cancelled", "refunded"}:
            raise ModelDeliveryRejected("billing operation failed delivery checks")

    def __exit__(self, exc_type, exc, tb):
        try:
            if exc_type is not None or not self.finished:
                self.finish("error")
        finally:
            _current_operation.reset(self.token)
            _last_attempt.reset(self.last_token)

    def before_attempt_payload(self, payload, route=None, provider_host=None):
        if self.before_network:
            self.before_network()
        output_limit = payload.get(
            "max_completion_tokens", payload.get("max_output_tokens", payload.get("max_tokens"))
        )
        if type(output_limit) is not int or output_limit <= 0:
            raise BillingContextMissing("a finite provider output token cap is required")
        if payload.get("web_search_options") or any(
            tool.get("type") != "function" for tool in payload.get("tools", ())
        ):
            raise BillingContextMissing("provider-paid builtin tools need a separate tariff")
        for message in payload.get("messages", ()):
            content = message.get("content")
            if isinstance(content, list) and any(p.get("type") != "text" for p in content):
                raise BillingContextMissing("multimodal token budgets are not supported")
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()
        # Estimate from the final wire body, including schemas, full history and
        # returned tool content. This is not a mathematical token/cash guarantee.
        input_limit = len(encoded) * 2 + 4096
        attempt = self.runtime.before_attempt(
            run_id=self.run_id,
            endpoint_id=route.endpoint.endpoint_id if route else "direct",
            route_id=route.context.route_id if route else None,
            model=payload["model"],
            input_limit=input_limit,
            output_limit=output_limit,
            request_hash=hashlib.sha256(encoded).hexdigest(),
            provider_host=provider_host,
            api_type="chat_completions",
            requested_effort=payload.get("reasoning_effort"),
            requested_service_tier=payload.get("service_tier"),
        )
        _last_attempt.set((self.run_id, attempt))
        return attempt

    def complete(
        self, attempt_id, response=None, *, outcome="error", failure_code=None, finish_reason=None
    ):
        counts = {}
        raw = getattr(response, "usage", None)
        if isinstance(response, dict):
            raw = response.get("usage")
        returned = (
            response.get("model")
            if isinstance(response, dict)
            else getattr(response, "model", None)
        )
        receipt = (
            response.get("id") if isinstance(response, dict) else getattr(response, "id", None)
        )
        if raw is not None:
            try:
                self.runtime.assert_usage_contract(attempt_id, raw)
                usage = normalized_usage(raw)
            except UnknownTokenUsage:
                self.runtime.complete_attempt(
                    attempt_id=attempt_id,
                    returned_model=returned,
                    provider_response_id=receipt,
                    outcome="error",
                    failure_code="invalid_token_usage",
                    usage_known=False,
                    raw_usage_json=json.dumps(_safe_usage_evidence(raw), sort_keys=True),
                )
                raise
            counts = dict(
                reasoning_tokens=usage.details.get("reasoning_tokens", 0),
                raw_usage_json=json.dumps(
                    {
                        "input_tokens": usage.input_tokens,
                        "output_tokens": usage.output_tokens,
                        "cache_read_tokens": usage.cache_read_tokens,
                        "cache_write_tokens": usage.cache_write_tokens,
                        "details": usage.details,
                    },
                    sort_keys=True,
                ),
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cache_read_tokens=usage.cache_read_tokens,
                cache_write_tokens=usage.cache_write_tokens,
            )
        choices = (
            response.get("choices", ())
            if isinstance(response, dict)
            else getattr(response, "choices", ())
        )
        reasons = [
            c.get("finish_reason") if isinstance(c, dict) else getattr(c, "finish_reason", None)
            for c in choices
        ]
        if finish_reason is not None:
            reasons = [finish_reason]
        rejected = outcome == "success" and any(r in {"length", "content_filter"} for r in reasons)
        if rejected:
            outcome = "limited" if "length" in reasons else "rejected"
        self.runtime.complete_attempt(
            attempt_id=attempt_id,
            returned_model=returned,
            provider_response_id=receipt,
            outcome=outcome,
            failure_code=failure_code,
            finish_reason=reasons[0] if reasons else None,
            returned_service_tier=response.get("service_tier")
            if isinstance(response, dict)
            else getattr(response, "service_tier", None),
            **counts,
        )
        if rejected:
            raise ModelDeliveryRejected("model output was limited or refused")
        if outcome == "success" and not counts:
            raise UnknownTokenUsage("paid response has no usage")


class _MeteredStream:
    def __init__(self, source, scope, attempt, continuous=False):
        self.source, self.scope, self.attempt = source, scope, attempt
        self.snapshots = UsageSnapshot(continuous)
        self.done = False

    async def __aenter__(self):
        try:
            await self.source.__aenter__()
        except BaseException:
            await self.close()
            raise
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.close()
        return False

    async def __aiter__(self):
        try:
            async for chunk in self.source:
                self.snapshots.accept(chunk)
                yield chunk
            self.scope.complete(
                self.attempt,
                self.snapshots.final_response,
                outcome="success",
                finish_reason=self.snapshots.finish_reason,
            )
            self.done = True
        except BaseException:
            if not self.done:
                self.scope.complete(
                    self.attempt,
                    self.snapshots.final_response,
                    outcome="error",
                    failure_code="stream_incomplete",
                    finish_reason=self.snapshots.finish_reason,
                )
                self.done = True
            raise

    async def close(self):
        try:
            await self.source.close()
        finally:
            if not self.done:
                self.scope.complete(
                    self.attempt,
                    self.snapshots.final_response,
                    outcome="error",
                    failure_code="stream_cancelled",
                    finish_reason=self.snapshots.finish_reason,
                )
                self.done = True


async def _wire_hook(request):
    state = _wire_request.get()
    if state is None:
        return
    payload = json.loads(request.content)
    state["attempt"] = state["scope"].before_attempt_payload(
        payload, state["route"], request.url.host
    )


class MeteredOpenAIChatModel(UsageSafeOpenAIChatModel):
    def __init__(self, *args, require_billing=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.require_billing = require_billing
        client = self.client._client
        if _wire_hook not in client.event_hooks["request"]:
            client.event_hooks["request"].append(_wire_hook)

    async def _completions_create(self, messages, stream, model_settings, model_request_parameters):
        scope = _current_operation.get()
        if scope is None:
            if self.require_billing:
                raise BillingContextMissing("paid invocation has no billing operation")
            return await super()._completions_create(
                messages, stream, model_settings, model_request_parameters
            )
        if self.client.max_retries != 0:
            raise BillingContextMissing("SDK automatic retries must be disabled")
        prior = _last_attempt.get()
        if (
            prior is not None
            and prior[0] == scope.run_id
            and messages
            and any(
                type(part).__name__ == "RetryPromptPart"
                for part in getattr(messages[-1], "parts", ())
            )
        ):
            scope.runtime.mark_attempt_error(prior[1], "output_validation_retry")
        state = {"scope": scope, "attempt": None, "route": current_model_route_scope()}
        token = _wire_request.set(state)
        try:
            value = await super()._completions_create(
                messages, stream, model_settings, model_request_parameters
            )
        except BaseException as error:
            if state["attempt"] is not None:
                scope.complete(
                    state["attempt"],
                    getattr(error, "body", None),
                    outcome="error",
                    failure_code=type(error).__name__,
                )
            raise
        finally:
            _wire_request.reset(token)
        if state["attempt"] is None:
            raise BillingContextMissing("provider transport did not pass the billing wire guard")
        if stream:
            return _MeteredStream(
                value,
                scope,
                state["attempt"],
                bool(model_settings.get("openai_continuous_usage_stats")),
            )
        scope.complete(state["attempt"], value, outcome="success")
        return value
