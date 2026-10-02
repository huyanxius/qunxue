"""Short SQLite transactions for reservations, paid attempts, exact credits and refunds.

No transaction remains open while calling a provider. Unknown provider cost stays
reserved across process restarts until an explicit receipt reconciles it.
"""

import json
from contextlib import contextmanager
from dataclasses import asdict
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid4, uuid5

from sqlalchemy import text

from qunxue_api.modules.billing import PICO_USD, PriceBook, Tariff, UnknownPrice
from qunxue_api.modules.billing import (
    BillingBudgetExceeded as BillingBudgetExceeded,
)
from qunxue_api.modules.billing import (
    BillingReplayBlocked as BillingReplayBlocked,
)
from qunxue_api.modules.billing import (
    BillingRouteMismatch as BillingRouteMismatch,
)

SCHEMA = (
    """CREATE TABLE billing_operations (
      run_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, fingerprint TEXT NOT NULL,
      status TEXT NOT NULL, hold_points INTEGER NOT NULL CHECK(hold_points >= 0),
      exempt INTEGER NOT NULL, price_json TEXT NOT NULL, credit_pico TEXT NOT NULL DEFAULT '0',
      original_credit_pico TEXT NOT NULL DEFAULT '0',
      charged_points INTEGER NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""",
    """CREATE TABLE billing_attempts (
      attempt_id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES billing_operations(run_id),
      endpoint_id TEXT NOT NULL, route_id TEXT, request_hash TEXT NOT NULL,
      requested_model TEXT NOT NULL, returned_model TEXT, provider_response_id TEXT,
      outcome TEXT NOT NULL, usage_state TEXT NOT NULL, billable INTEGER NOT NULL DEFAULT 0,
      input_limit INTEGER NOT NULL, output_limit INTEGER NOT NULL,
      reserved_cost_pico INTEGER NOT NULL CHECK(reserved_cost_pico >= 0),
      reference_cost_pico INTEGER, procurement_cost_pico INTEGER,
      input_tokens INTEGER, cache_read_tokens INTEGER, cache_write_tokens INTEGER,
      output_tokens INTEGER, reasoning_tokens INTEGER, raw_usage_json TEXT,
      provider_host TEXT, api_type TEXT, requested_effort TEXT, requested_service_tier TEXT,
      returned_service_tier TEXT, finish_reason TEXT,
      procurement_status TEXT NOT NULL DEFAULT 'pending',
      overrun_cost_pico INTEGER NOT NULL DEFAULT 0,
      failure_code TEXT, price_json TEXT NOT NULL,
      created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""",
    """CREATE TABLE billing_precision (
      user_id TEXT PRIMARY KEY, total_credit_pico TEXT NOT NULL)""",
    "CREATE INDEX ix_billing_operations_user_status ON billing_operations(user_id,status)",
    "CREATE INDEX ix_billing_attempts_run ON billing_attempts(run_id)",
    (
        "CREATE UNIQUE INDEX uq_billing_provider_receipt ON billing_attempts "
        "(provider_host,provider_response_id) WHERE provider_response_id IS NOT NULL"
    ),
)


def create_billing_tables(engine):
    """Create an empty billing namespace without changing accounts or old ledger rows."""
    with engine.begin() as conn:
        for statement in SCHEMA:
            conn.execute(text(statement))


class DurableBilling:
    def __init__(
        self,
        engine,
        *,
        price_book: PriceBook,
        max_attempt_pico: int,
        max_operation_pico: int,
        daily_budget_pico: int,
        max_attempts: int = 64,
        clock=None,
    ):
        values = max_attempt_pico, max_operation_pico, daily_budget_pico, max_attempts
        if any(type(n) is not int or n <= 0 for n in values):
            raise ValueError("finite positive billing budgets are required")
        self.engine = engine
        self.book = price_book
        self.max_attempt_pico = max_attempt_pico
        self.max_operation_pico = max_operation_pico
        self.daily_budget_pico = daily_budget_pico
        self.max_attempts = max_attempts
        self.clock = clock or (lambda: datetime.now(UTC))

    @contextmanager
    def _transaction(self):
        with self.engine.connect() as conn:
            conn.execute(text("BEGIN IMMEDIATE"))
            try:
                yield conn
                conn.commit()
            except BaseException:
                conn.rollback()
                raise

    def _now(self):
        return self.clock().isoformat()

    @staticmethod
    def _one(conn, sql, **args):
        return conn.execute(text(sql), args).mappings().first()

    @staticmethod
    def _snapshot(book):
        return json.dumps(
            {
                "credits_per_usd": book.credits_per_usd,
                "version": book.version,
                "aliases": dict(book.aliases),
                "usage_policies": dict(book.usage_policies),
                "tariffs": {k: asdict(v) for k, v in book.tariffs.items()},
                "deepseek_time_basis": book.deepseek_time_basis,
                "calendar_version": book.calendar_version,
                "reference_band": book.reference_band,
                "dispatch_at": book.dispatch_at,
            },
            sort_keys=True,
        )

    @staticmethod
    def _book(snapshot):
        data = json.loads(snapshot)
        return PriceBook(
            credits_per_usd=data["credits_per_usd"],
            version=data["version"],
            aliases=data["aliases"],
            usage_policies=data.get("usage_policies", {}),
            deepseek_time_basis=data.get("deepseek_time_basis"),
            calendar_version=data.get("calendar_version"),
            reference_band=data.get("reference_band"),
            dispatch_at=data.get("dispatch_at"),
            tariffs={k: Tariff(**v) for k, v in data["tariffs"].items()},
        )

    def _available(self, conn, user_id):
        row = self._one(
            conn, "SELECT balance FROM credit_accounts WHERE user_id=:user", user=user_id
        )
        if row is None:
            raise BillingBudgetExceeded("credit account is missing", reason="credits_depleted")
        held = conn.scalar(
            text(
                "SELECT coalesce(sum(hold_points),0) FROM billing_operations "
                "WHERE user_id=:user AND status='active'"
            ),
            {"user": user_id},
        )
        return max(0, row["balance"] - held)

    def available_balance(self, user_id):
        with self.engine.connect() as conn:
            return self._available(conn, str(user_id))

    def start(self, *, user_id, run_id, fingerprint, exempt=False):
        run_id, user_id = str(run_id), str(user_id)
        with self._transaction() as conn:
            if self._one(
                conn, "SELECT run_id FROM billing_operations WHERE run_id=:run", run=run_id
            ):
                # No provider idempotency guarantee: a crashed invocation cannot be resent.
                raise BillingReplayBlocked("operation already exists; use its persisted outcome")
            available = 0 if exempt else self._available(conn, user_id)
            cap = (self.max_operation_pico * self.book.credits_per_usd + PICO_USD - 1) // PICO_USD
            hold = 0 if exempt else min(available, cap)
            if not exempt and hold == 0:
                balance = conn.scalar(
                    text("SELECT balance FROM credit_accounts WHERE user_id=:user"),
                    {"user": user_id},
                )
                raise BillingBudgetExceeded(
                    "no available credits",
                    reason="credits_frozen" if balance else "credits_depleted",
                )
            now = self._now()
            conn.execute(
                text(
                    "INSERT INTO billing_operations "
                    "(run_id,user_id,fingerprint,status,hold_points,exempt,price_json,creat"
                    "ed_at,updated_at) "
                    "VALUES (:run,:user,:fingerprint,'active',:hold,:exempt,:price,:now,:now)"
                ),
                {
                    "run": run_id,
                    "user": user_id,
                    "fingerprint": fingerprint,
                    "hold": hold,
                    "exempt": int(exempt),
                    "price": self._snapshot(self.book),
                    "now": now,
                },
            )
        return run_id

    def _risk(self, conn):
        midnight = self.clock().astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        return conn.scalar(
            text(
                "SELECT coalesce(sum(CASE WHEN reference_cost_pico IS NULL "
                "THEN reserved_cost_pico WHEN updated_at >= :day THEN "
                "reference_cost_pico ELSE 0 END),0) "
                "FROM billing_attempts"
            ),
            {"day": midnight.isoformat()},
        )

    def operator_risk_pico(self):
        with self.engine.connect() as conn:
            return self._risk(conn)

    def before_attempt(
        self,
        *,
        run_id,
        endpoint_id,
        model,
        input_limit,
        output_limit,
        request_hash,
        route_id=None,
        provider_host=None,
        api_type="chat_completions",
        requested_effort=None,
        requested_service_tier=None,
    ):
        with self._transaction() as conn:
            run = self._one(
                conn, "SELECT * FROM billing_operations WHERE run_id=:run", run=str(run_id)
            )
            if run is None or run["status"] != "active":
                raise BillingReplayBlocked("operation is not active")
            if requested_service_tier not in {None, "default", "standard"}:
                raise UnknownPrice("requested service tier has no configured tariff")
            book = self._book(run["price_json"]).lock_dispatch(model, self.clock())
            reserved = book.maximum_cost(model, input_limit, output_limit)
            aggregate = self._one(
                conn,
                "SELECT count(*) AS n, "
                "coalesce(sum(coalesce(reference_cost_pico,reserved_cost_pico)),0) "
                "AS cost,coalesce(sum(CASE WHEN billable=1 THEN reference_cost_pico "
                "WHEN outcome='in_flight' THEN reserved_cost_pico ELSE 0 END),0) "
                "AS user_cost FROM billing_attempts WHERE run_id=:run",
                run=str(run_id),
            )
            operation_risk = aggregate["cost"] + reserved
            user_risk = aggregate["user_cost"] + reserved
            max_credit = (user_risk * book.credits_per_usd + PICO_USD - 1) // PICO_USD
            if (
                reserved > self.max_attempt_pico
                or aggregate["n"] >= self.max_attempts
                or operation_risk > self.max_operation_pico
                or self._risk(conn) + reserved > self.daily_budget_pico
            ):
                raise BillingBudgetExceeded("model request exceeds reserved budget")
            if not run["exempt"] and max_credit > run["hold_points"]:
                raise BillingBudgetExceeded(
                    "request needs more available credits", reason="credits_depleted"
                )
            attempt = str(uuid4())
            now = self._now()
            conn.execute(
                text(
                    "INSERT INTO billing_attempts "
                    "(attempt_id,run_id,endpoint_id,route_id,request_hash,requested_model,o"
                    "utcome,usage_state,"
                    "input_limit,output_limit,reserved_cost_pico,price_json,provider_host,a"
                    "pi_type,requested_effort,requested_service_tier,created_at,updated_at)"
                    " "
                    "VALUES "
                    "(:id,:run,:endpoint,:route,:hash,:model,'in_flight','unknown',:i,:o,:c"
                    "ost,"
                    ":price,:provider,:api,:effort,:tier,:now,:now)"
                ),
                {
                    "id": attempt,
                    "run": str(run_id),
                    "endpoint": endpoint_id,
                    "route": str(route_id) if route_id else None,
                    "hash": request_hash,
                    "model": model,
                    "i": input_limit,
                    "o": output_limit,
                    "cost": reserved,
                    "price": self._snapshot(book),
                    "provider": provider_host,
                    "api": api_type,
                    "effort": requested_effort,
                    "tier": requested_service_tier,
                    "now": now,
                },
            )
            conn.execute(
                text("UPDATE billing_operations SET updated_at=:now WHERE run_id=:run"),
                {"now": now, "run": str(run_id)},
            )
        return attempt

    def assert_usage_contract(self, attempt_id, raw):
        from collections.abc import Mapping

        from qunxue_api.adapters.model.token_usage import UnknownTokenUsage

        if hasattr(raw, "model_dump"):
            raw = raw.model_dump(exclude_none=True)
        if not isinstance(raw, Mapping):
            raise UnknownTokenUsage("missing provider usage")
        with self.engine.connect() as conn:
            row = self._one(
                conn, "SELECT * FROM billing_attempts WHERE attempt_id=:id", id=attempt_id
            )
        book = self._book(row["price_json"])
        model = book.aliases.get(row["requested_model"], row["requested_model"])
        if model == "deepseek-flash":
            if "prompt_cache_hit_tokens" not in raw or "prompt_cache_miss_tokens" not in raw:
                raise UnknownTokenUsage("DeepSeek cache partition is missing")
            return
        details = raw.get("prompt_tokens_details", raw.get("input_tokens_details", {}))
        if not isinstance(details, Mapping):
            raise UnknownTokenUsage("invalid provider input details")
        present = "cached_tokens" in details and (
            "cache_write_tokens" in details or "cache_creation_input_tokens" in raw
        )
        policy_key = f"{row['provider_host']}:{row['requested_model']}"
        if not present and book.usage_policies.get(policy_key) != "omitted_cache_subsets_are_zero":
            raise UnknownTokenUsage(
                "chargeable cache subtypes need counters or explicit zero-omission policy"
            )

    def complete_attempt(
        self,
        *,
        attempt_id,
        usage_known=True,
        input_tokens=None,
        output_tokens=None,
        cache_read_tokens=0,
        cache_write_tokens=0,
        returned_model=None,
        provider_response_id=None,
        outcome="error",
        failure_code=None,
        reasoning_tokens=None,
        raw_usage_json=None,
        finish_reason=None,
        returned_service_tier=None,
    ):
        exceeded = False
        mismatch = False
        price_error = None
        with self._transaction() as conn:
            row = self._one(
                conn, "SELECT * FROM billing_attempts WHERE attempt_id=:id", id=attempt_id
            )
            if row is None:
                raise BillingReplayBlocked("attempt is missing")
            if row["usage_state"] == "known":
                return
            cost = None
            if usage_known and input_tokens is not None and output_tokens is not None:
                book = self._book(row["price_json"])
                mismatch = bool(
                    returned_model
                    and book.aliases.get(returned_model, returned_model)
                    != book.aliases.get(row["requested_model"], row["requested_model"])
                )
                # The returned identity, including aliases, must have an explicit tariff.
                try:
                    if not returned_model:
                        raise UnknownPrice("returned provider model identity is missing")
                    if returned_service_tier not in {None, "default", "standard"}:
                        raise UnknownPrice("returned service tier has no configured tariff")
                    cost = book.cost_pico_usd(
                        returned_model or row["requested_model"],
                        input_tokens,
                        output_tokens,
                        cache_read_tokens,
                        cache_write_tokens,
                    )
                except UnknownPrice as error:
                    price_error = error
                    outcome = "error"
                    failure_code = "unknown_returned_price"
                exceeded = (
                    (cost is not None and cost > row["reserved_cost_pico"])
                    or input_tokens > row["input_limit"]
                    or output_tokens > row["output_limit"]
                )
                if exceeded:
                    outcome = "overrun"
                elif mismatch:
                    outcome = "model_mismatch"
            operation = self._one(
                conn, "SELECT status FROM billing_operations WHERE run_id=:run", run=row["run_id"]
            )
            billable = int(outcome == "success" and operation["status"] == "active")
            conn.execute(
                text(
                    "UPDATE billing_attempts SET "
                    "billable=:billable,outcome=:outcome,usage_state=:state,"
                    "input_tokens=:i,output_tokens=:o,cache_read_tokens=:c,cache_write_tokens=:w,"
                    "reference_cost_pico=:cost,returned_model=:model,provider_response_id=:receipt,"
                    "reasoning_tokens=:reasoning,raw_usage_json=:raw,finish_reason=:finish,"
                    "returned_service_tier=:tier,"
                    "overrun_cost_pico=:overrun,failure_code=:failure,updated_at=:now "
                    "WHERE attempt_id=:id"
                ),
                {
                    "outcome": outcome,
                    "billable": billable,
                    "state": "known"
                    if cost is not None
                    else "unpriced"
                    if price_error
                    else "unknown",
                    "i": input_tokens,
                    "o": output_tokens,
                    "c": cache_read_tokens,
                    "w": cache_write_tokens,
                    "cost": cost,
                    "model": returned_model,
                    "receipt": provider_response_id,
                    "failure": failure_code,
                    "reasoning": reasoning_tokens,
                    "raw": raw_usage_json,
                    "finish": finish_reason,
                    "tier": returned_service_tier,
                    "overrun": max(0, (cost or 0) - row["reserved_cost_pico"]),
                    "now": self._now(),
                    "id": attempt_id,
                },
            )
        if price_error:
            raise price_error
        if mismatch:
            raise BillingRouteMismatch("returned model differs from the locked route")
        if exceeded:
            raise BillingBudgetExceeded("provider usage exceeded its request reservation")

    def mark_attempt_error(self, attempt_id, failure_code):
        with self._transaction() as conn:
            conn.execute(
                text(
                    "UPDATE billing_attempts SET outcome='error',billable=0,failure_code=:code "
                    "WHERE attempt_id=:id AND outcome='success'"
                ),
                {"id": attempt_id, "code": failure_code},
            )

    def _ledger(self, conn, run, points, *, refund=False):
        balance = conn.scalar(
            text("SELECT balance FROM credit_accounts WHERE user_id=:user"),
            {"user": run["user_id"]},
        )
        ident = (
            str(uuid5(NAMESPACE_URL, "billing-refund:" + run["run_id"]))
            if refund
            else run["run_id"]
        )
        totals = self._one(
            conn,
            "SELECT coalesce(sum(input_tokens),0) AS i, "
            "coalesce(sum(output_tokens),0) AS o FROM billing_attempts WHERE run_id=:run "
            "AND outcome='success'",
            run=run["run_id"],
        )
        conn.execute(
            text(
                "INSERT INTO credit_ledger "
                "(entry_id,user_id,run_id,kind,points,balance_after,input_tokens,output"
                "_tokens,model,created_at) "
                "VALUES (:id,:user,:id,'usage',:points,:balance,:i,:o,:model,:now)"
            ),
            {
                "id": ident,
                "user": run["user_id"],
                "points": points,
                "balance": balance,
                "i": 0 if refund else totals["i"],
                "o": 0 if refund else totals["o"],
                "model": "billing-refund" if refund else "priced-attempts",
                "now": self._now(),
            },
        )

    def finish(self, *, run_id, outcome):
        if outcome not in {"success", "error", "cancelled"}:
            raise ValueError("invalid billing operation outcome")
        with self._transaction() as conn:
            run = self._one(
                conn, "SELECT * FROM billing_operations WHERE run_id=:run", run=str(run_id)
            )
            if run is None or run["status"] in {"error", "cancelled", "refunded"}:
                return
            if run["status"] == "success" and outcome == "success":
                return
            attempts = (
                conn.execute(
                    text("SELECT * FROM billing_attempts WHERE run_id=:run"), {"run": str(run_id)}
                )
                .mappings()
                .all()
            )
            if outcome == "success" and any(
                a["outcome"] in {"in_flight", "overrun", "model_mismatch", "limited", "rejected"}
                or (a["outcome"] == "success" and a["usage_state"] != "known")
                for a in attempts
            ):
                outcome = "error"
            if outcome == "success" and attempts and not any(a["billable"] for a in attempts):
                outcome = "error"
            book = self._book(run["price_json"])
            numerator = (
                sum(
                    a["reference_cost_pico"] or 0
                    for a in attempts
                    if a["outcome"] == "success" and a["billable"]
                )
                * book.credits_per_usd
            )
            previous = self._one(
                conn,
                "SELECT total_credit_pico FROM billing_precision WHERE user_id=:user",
                user=run["user_id"],
            )
            previous_total = int(previous["total_credit_pico"]) if previous else 0
            new_total = previous_total
            points = 0
            if not run["exempt"]:
                if run["status"] == "success":
                    new_total -= int(run["credit_pico"])
                    points = previous_total // PICO_USD - new_total // PICO_USD
                elif outcome == "success":
                    new_total += numerator
                    points = new_total // PICO_USD - previous_total // PICO_USD
                    account = self._one(
                        conn,
                        "SELECT balance FROM credit_accounts WHERE user_id=:user",
                        user=run["user_id"],
                    )
                    # An overrun is fully borne by the operator, never capped silently.
                    if points > run["hold_points"] or points > account["balance"]:
                        outcome = "error"
                        points = 0
                        new_total = previous_total
                if new_total != previous_total:
                    conn.execute(
                        text(
                            "INSERT INTO billing_precision(user_id,total_credit_pico) "
                            "VALUES (:user,:total) ON CONFLICT(user_id) DO UPDATE SET "
                            "total_credit_pico=excluded.total_credit_pico"
                        ),
                        {"user": run["user_id"], "total": str(new_total)},
                    )
                    change = points if run["status"] == "success" else -points
                    conn.execute(
                        text(
                            "UPDATE credit_accounts SET balance=balance+:change,updated_at=:now "
                            "WHERE user_id=:user"
                        ),
                        {"change": change, "user": run["user_id"], "now": self._now()},
                    )
                    self._ledger(conn, run, change, refund=run["status"] == "success")
            status = "refunded" if run["status"] == "success" else outcome
            conn.execute(
                text(
                    "UPDATE billing_operations SET status=:status,hold_points=0,"
                    "credit_pico=:exact,original_credit_pico=CASE WHEN original_credit_pico='0' "
                    "THEN :exact ELSE original_credit_pico END,charged_points=:points,"
                    "updated_at=:now WHERE run_id=:run"
                ),
                {
                    "status": status,
                    "exact": str(numerator if outcome == "success" else 0),
                    "points": points if outcome == "success" else 0,
                    "now": self._now(),
                    "run": str(run_id),
                },
            )

    def recover_stale(self, *, before):
        with self.engine.connect() as conn:
            ids = conn.scalars(
                text(
                    "SELECT run_id FROM billing_operations WHERE status='active' "
                    "AND updated_at < :before"
                ),
                {"before": before.isoformat()},
            ).all()
        for run_id in ids:
            self.finish(run_id=run_id, outcome="error")
