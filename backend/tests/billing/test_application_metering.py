# ruff: noqa: F811
from dataclasses import replace
from uuid import UUID

import pytest
from test_agent_conversation import _FakeAgentTools, _UsageRunner
from test_durable_billing import balance, wallet  # noqa: F401

from qunxue_api.adapters.model.metering import OperationScope, _current_operation
from qunxue_api.application.disciplinary_agent import DisciplinaryAgentApplication
from qunxue_api.modules.agent_conversation import ConversationService


class Operations:
    def __init__(self, runtime):
        self.runtime = runtime

    def open(self, **scope):
        return OperationScope(
            self.runtime,
            user_id="user",
            run_id=scope["run_id"],
            fingerprint="synthetic",
            before_network=scope["before_network"],
        )

    def close(self, **operation):
        self.runtime.finish(**operation)


class Runner(_UsageRunner):
    def run(self, **kwargs):
        scope = _current_operation.get()
        assert scope is not None
        attempt = scope.runtime.before_attempt(
            run_id=scope.run_id,
            endpoint_id="primary",
            model="gpt-6.1-sol",
            input_limit=1000,
            output_limit=1000,
            request_hash="synthetic",
        )
        scope.runtime.complete_attempt(
            attempt_id=attempt,
            input_tokens=600,
            output_tokens=800,
            returned_model="gpt-6.1-sol",
            outcome="success",
        )
        return replace(super().run(**kwargs), model="gpt-6.1-sol")


@pytest.mark.parametrize("fail_finalize", [False, True])
def test_application_commits_delivery_before_settlement_and_refunds_finalizer_error(
    wallet, fail_finalize
):
    runtime, engine = wallet

    class Tools(_FakeAgentTools):
        def finalize_agent_turn(self, **kwargs):
            if fail_finalize:
                raise ValueError("synthetic save failure")

    application = DisciplinaryAgentApplication(
        conversations=ConversationService.in_memory(),
        runner=Runner(),
        tools_factory=Tools,
        billing=Operations(runtime),
    )
    args = dict(
        user_id=UUID(int=1), conversation_id=None, prompt="synthetic", idempotency_key="synthetic"
    )
    if fail_finalize:
        with pytest.raises(ValueError, match="synthetic save failure"):
            application.run_turn(**args)
        assert balance(engine) == 10000
    else:
        application.run_turn(**args)
        application.run_turn(**args)
        assert balance(engine) == 9908
    with engine.connect() as c:
        from sqlalchemy import text

        assert c.scalar(text("SELECT sum(reference_cost_pico) FROM billing_attempts")) == 9200000000
