from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import text
from test_account_management_api import (
    TEST_ADMIN_EMAIL,
    TEST_ADMIN_PASSWORD,
    login,
    login_admin,
    register,
)

from qunxue_api.adapters.sqlite.database import Database
from qunxue_api.bootstrap import create_app
from qunxue_api.modules.account_management import service as account_service
from qunxue_api.settings import Settings

TEST_SIGNING_KEY = "synthetic-independent-signing-key"
CHANGED_ADMIN_PASSWORD = "changed-admin-passphrase"


@pytest.fixture
def bootstrap_database_url(tmp_path, monkeypatch, alembic_config) -> str:
    database_url = f"sqlite:///{tmp_path / 'bootstrap.db'}"
    monkeypatch.setenv("QUNXUE_DATABASE_URL", database_url)
    command.upgrade(alembic_config, "head")

    def reject_network(*args, **kwargs):
        pytest.fail("Account bootstrap must not make external HTTP requests")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", reject_network)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", reject_network)
    return database_url


@contextmanager
def account_client(database_url: str, **configuration) -> Iterator[TestClient]:
    database = Database(database_url)
    settings = Settings(
        _env_file=None,
        database_url=database_url,
        runtime_mode="mock",
        **configuration,
    )
    try:
        app = create_app(settings=settings, database=database, require_email_verification=False)
        with TestClient(app) as client:
            yield client
    finally:
        database.engine.dispose()


@pytest.mark.parametrize(
    ("initial_key", "runtime_key", "preserve_signatures"),
    [
        (None, TEST_ADMIN_PASSWORD, True),
        (TEST_SIGNING_KEY, TEST_SIGNING_KEY, True),
        (None, TEST_SIGNING_KEY, False),
    ],
    ids=["legacy-key-relocation", "independent-key", "legacy-token-consumption"],
)
def test_routes_and_credentials_survive_removing_bootstrap_configuration(
    bootstrap_database_url, initial_key, runtime_key, preserve_signatures, monkeypatch,
) -> None:
    now = [datetime(2026, 10, 1, tzinfo=UTC)]
    monkeypatch.setattr(account_service, "datetime", SimpleNamespace(now=lambda _tz: now[0]))
    reset_key, batch_key = str(uuid4()), str(uuid4())
    with account_client(
        bootstrap_database_url,
        account_initial_admin_email=TEST_ADMIN_EMAIL,
        account_initial_admin_password=TEST_ADMIN_PASSWORD,
        account_signing_key=initial_key,
    ) as client:
        member = register(client, "restart-member@example.com")["user"]["user_id"]
        login_admin(client)
        reset_path = f"/api/admin/users/{member}/password-reset-links"
        reset = client.post(reset_path, headers={"Idempotency-Key": reset_key})
        batch = client.post(
            "/api/admin/credit-redemption-codes",
            headers={"Idempotency-Key": batch_key},
            json={"count": 1, "expires_in_days": 7},
        )
        assert reset.status_code == batch.status_code == 201
        changed = client.post(
            "/api/account/password/change",
            headers={"Idempotency-Key": str(uuid4())},
            json={
                "current_password": TEST_ADMIN_PASSWORD,
                "new_password": CHANGED_ADMIN_PASSWORD,
                "revoke_other_sessions": True,
            },
        )
        assert changed.status_code == 200
        cookies = dict(client.cookies)

    # A new engine and app reconnect to the same persisted database, without either
    # bootstrap credential. Existing cookies and signed credentials must still work.
    with account_client(
        bootstrap_database_url, account_signing_key=runtime_key,
    ) as restarted:
        restarted.cookies.update(cookies)
        account = restarted.get("/api/account")
        assert account.status_code == 200
        assert account.json()["is_protected_admin"] is True
        assert restarted.get("/api/admin/users").status_code == 200
        assert restarted.get("/api/account/credits").json()["is_unlimited"] is True
        restarted.cookies.clear()
        # Restarting must preserve the login gate; independent sign-ins wait out its cooldown.
        assert restarted.post(
            "/api/session/login",
            headers={"Idempotency-Key": str(uuid4())},
            json={"email": TEST_ADMIN_EMAIL, "password": CHANGED_ADMIN_PASSWORD},
        ).status_code == 401
        now[0] += timedelta(minutes=1)
        login(restarted, TEST_ADMIN_EMAIL, password=CHANGED_ADMIN_PASSWORD)

        if preserve_signatures:
            replayed_reset = restarted.post(reset_path, headers={"Idempotency-Key": reset_key})
            assert replayed_reset.status_code == 201
            assert replayed_reset.json()["reset_token"] == reset.json()["reset_token"]
            replayed_batch = restarted.post(
                "/api/admin/credit-redemption-codes",
                headers={"Idempotency-Key": batch_key},
                json={"count": 1, "expires_in_days": 7},
            )
            assert replayed_batch.status_code == 201
            assert replayed_batch.json()["codes"] == batch.json()["codes"]

        consumed = restarted.post(
            "/api/account/password-resets/consume",
            headers={"Idempotency-Key": str(uuid4())},
            json={"token": reset.json()["reset_token"], "new_password": "reset-member-passphrase"},
        )
        assert consumed.status_code == 200
        now[0] += timedelta(seconds=2)
        login(restarted, "restart-member@example.com", password="reset-member-passphrase")
        redeemed = restarted.post(
            "/api/account/credit-redemptions",
            headers={"Idempotency-Key": str(uuid4())},
            json={"code": batch.json()["codes"][0]},
        )
        assert redeemed.status_code == 200
        with restarted.app.state.database.engine.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM users")) == 2
            assert connection.scalar(text(
                "SELECT count(*) FROM account_audit_events WHERE action = 'admin.provisioned'"
            )) == 1


def test_signing_configuration_alone_does_not_provision_an_administrator(
    bootstrap_database_url,
) -> None:
    with account_client(
        bootstrap_database_url, account_signing_key=TEST_SIGNING_KEY,
    ) as client:
        assert client.get("/api/account").status_code == 401
        with client.app.state.database.engine.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM users")) == 0
            assert connection.scalar(text(
                "SELECT initial_admin_provisioned FROM account_system_state WHERE singleton_id = 1"
            )) == 0
