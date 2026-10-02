import importlib.util
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import create_engine, text


def test_additive_migration_keeps_legacy_balance_and_ledger(tmp_path):
    migration = next(
        (Path(__file__).parents[2] / "migrations/versions").glob("*_durable_billing.py")
    )
    spec = importlib.util.spec_from_file_location("synthetic_migration", migration)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    engine = create_engine(f"sqlite:///{tmp_path}/legacy.db")
    with engine.begin() as c:
        c.execute(text("CREATE TABLE credit_accounts(user_id TEXT PRIMARY KEY,balance INTEGER)"))
        c.execute(text("CREATE TABLE credit_ledger(entry_id TEXT PRIMARY KEY,points INTEGER)"))
        c.execute(text("INSERT INTO credit_accounts VALUES ('legacy',8765)"))
        c.execute(text("INSERT INTO credit_ledger VALUES ('old-evidence',-1235)"))
        module.op = SimpleNamespace(execute=lambda sql: c.execute(text(sql)))
        module.upgrade()
        assert c.execute(text("SELECT * FROM credit_accounts")).all() == [("legacy", 8765)]
        assert c.execute(text("SELECT * FROM credit_ledger")).all() == [("old-evidence", -1235)]
        assert c.execute(text("SELECT * FROM billing_operations")).all() == []
        columns = {r[1] for r in c.execute(text("PRAGMA table_info(billing_attempts)"))}
        assert {"billable", "procurement_cost_pico", "raw_usage_json", "provider_host"} <= columns
    engine.dispose()
