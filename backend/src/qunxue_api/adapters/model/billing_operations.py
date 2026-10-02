"""Application-facing scope factory, assembled once by bootstrap."""

import hashlib
import json

from qunxue_api.adapters.model.metering import BillingContextMissing, OperationScope
from qunxue_api.adapters.sqlite.billing_repository import SqliteCreditRepository
from qunxue_api.modules.billing import CreditService


class SqliteBillingOperations:
    def __init__(self, database, runtime, exempt_user_ids=(), phase_policies=None):
        self.database = database
        self.runtime = runtime
        self.exempt_user_ids = exempt_user_ids
        self.phase_policies = phase_policies or {}

    def open(self, *, user_id, run_id, payload, before_network=None, phase="agent_turn"):
        policy = "user" if phase == "agent_turn" else self.phase_policies.get(phase)
        if phase in {"model_probe", "graph_topic_naming"} and policy != "operator":
            raise BillingContextMissing("optional naming and probes must be operator-funded")
        if policy not in {"user", "operator"}:
            raise BillingContextMissing(
                "this standalone model phase needs an explicit billing policy"
            )
        if self.runtime is None:
            raise BillingContextMissing(
                "billing conversion, price version and risk budgets are required"
            )
        if policy == "user":
            with self.database.session() as session:
                CreditService(SqliteCreditRepository(session)).summary(user_id=user_id, limit=1)
        fingerprint = hashlib.sha256(
            json.dumps(payload, default=str, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        return OperationScope(
            self.runtime,
            user_id=user_id,
            run_id=run_id,
            fingerprint=fingerprint,
            exempt=policy == "operator"
            or str(user_id)
            in {
                str(u)
                for u in (
                    self.exempt_user_ids()
                    if callable(self.exempt_user_ids)
                    else self.exempt_user_ids
                )
            },
            before_network=before_network,
        )

    def close(self, *, run_id, outcome):
        if self.runtime:
            self.runtime.finish(run_id=run_id, outcome=outcome)
