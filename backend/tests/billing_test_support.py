"""Explicit synthetic budgets for tests that intentionally invoke paid boundaries."""

from qunxue_api.adapters.sqlite.durable_billing import DurableBilling, create_billing_tables
from qunxue_api.modules.billing.pricing import PriceBook


def synthetic_billing_runtime(engine, *, aliases=None, create_tables=False):
    if create_tables:
        create_billing_tables(engine)
    return DurableBilling(
        engine,
        price_book=PriceBook(
            credits_per_usd=10000,
            version="synthetic-ci",
            aliases=aliases
            or {
                "test-model": "gpt-6-luna",
                "deepseek-v4-flash": "gpt-6-luna",
            },
        ),
        max_attempt_pico=10**11,
        max_operation_pico=10**11,
        daily_budget_pico=10**12,
        max_attempts=10,
    )


def configure_synthetic_billing(app, *, phase):
    operations = app.state.billing_operations
    operations.runtime = synthetic_billing_runtime(app.state.database.engine)
    operations.phase_policies[phase] = "operator"
