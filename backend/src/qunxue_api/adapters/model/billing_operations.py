"""Application-facing scope factory, assembled once by bootstrap."""

import hashlib
import json
from contextlib import contextmanager
from copy import copy

from qunxue_api.adapters.model.metering import BillingContextMissing, OperationScope
from qunxue_api.adapters.sqlite.billing_repository import SqliteCreditRepository
from qunxue_api.modules.billing import CreditService


class SqliteBillingOperations:
    def __init__(self, database, runtime, exempt_user_ids=(), phase_policies=None):
        self.database = database
        self.runtime = runtime
        self.exempt_user_ids = exempt_user_ids
        self.phase_policies = phase_policies or {}
        self.session = None

    def bound_to(self, session):
        operations = copy(self)
        operations.session = session
        return operations

    @contextmanager
    def atomic(self):
        # Python sqlite3 legacy mode does not BEGIN for SAVEPOINT. Without an
        # explicit outer transaction, RELEASE commits before Session.commit().
        # Bind only these existing business savepoints to a real transaction.
        connection = self.session.connection()
        if (
            connection.dialect.name == "sqlite"
            and not connection.connection.driver_connection.in_transaction
        ):
            connection.exec_driver_sql("BEGIN IMMEDIATE")
        with self.session.begin_nested():
            yield

    def _settlement_connection(self):
        self.session.flush()
        return self.session.connection()

    def open(self, *, user_id, run_id, payload, before_network=None, phase="agent_turn",
             resume=False):
        policy = (
            "user" if phase in {"agent_turn", "user_research"} else self.phase_policies.get(phase)
        )
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
            resume=resume,
            settlement_connection=self._settlement_connection if self.session is not None else None,
        )

    def close(self, *, run_id, outcome):
        if self.runtime:
            self.runtime.finish(run_id=run_id, outcome=outcome)
