"""Add immutable billing evidence; existing balances and ledger remain untouched."""

from alembic import op

revision = "20261002_0463"
down_revision = "20261002_0462"
branch_labels = None
depends_on = None

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


def upgrade():
    for statement in SCHEMA:
        op.execute(statement)


def downgrade():
    raise RuntimeError("billing financial evidence cannot be removed by automatic downgrade")
