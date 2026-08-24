import json
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from qunxue_api.account_extension import install_account_management
from qunxue_api.adapters.security import Argon2PasswordHasher
from qunxue_api.adapters.sqlite import (
    AccountAuditEventRow,
    ModelInvocationRow,
    ResearchTaskRow,
    UserRow,
)
from qunxue_api.adapters.sqlite.billing_model import CreditAccountRow
from qunxue_api.adapters.sqlite.billing_repository import SqliteCreditRepository
from qunxue_api.adapters.sqlite.database import Database
from qunxue_api.bootstrap import create_app
from qunxue_api.settings import Settings

TEST_ADMIN_EMAIL = "test-admin@example.com"
TEST_ADMIN_PASSWORD = "test-initial-admin-passphrase"


def test_create_app_installs_account_routes_when_admin_secret_is_configured(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    alembic_config: Config,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'account-bootstrap.db'}"
    monkeypatch.setenv("QUNXUE_DATABASE_URL", database_url)
    command.upgrade(alembic_config, "head")
    settings = Settings(
        _env_file=None,
        database_url=database_url,
        runtime_mode="mock",
        account_initial_admin_email=TEST_ADMIN_EMAIL,
        account_initial_admin_password=TEST_ADMIN_PASSWORD,
    )
    database = Database(database_url)
    app = create_app(settings=settings, database=database)
    try:
        assert "/api/account" in app.openapi()["paths"]
        assert "/api/admin/users" in app.openapi()["paths"]
        with TestClient(app) as test_client:
            login_admin(test_client)
            assert test_client.get("/api/account").json()["role"] == "admin"
    finally:
        database.engine.dispose()


@pytest.fixture
def client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    alembic_config: Config,
) -> Iterator[TestClient]:
    database_url = f"sqlite:///{tmp_path / 'account-test.db'}"
    monkeypatch.setenv("QUNXUE_DATABASE_URL", database_url)
    settings = Settings(
        _env_file=None,
        database_url=database_url,
        runtime_mode="mock",
        model_base_url=None,
        model_api_key=None,
        model_name=None,
        model_extra_headers={},
        model_sft_resource_id=None,
    )
    command.upgrade(alembic_config, "head")
    database = Database(database_url)
    app = create_app(
        settings=settings,
        database=database,
        require_email_verification=False,
    )
    install_account_management(
        app,
        database=database,
        password_hasher=Argon2PasswordHasher(),
        initial_admin_email=TEST_ADMIN_EMAIL,
        initial_admin_password=TEST_ADMIN_PASSWORD,
    )
    with TestClient(app) as test_client:
        yield test_client
    database.engine.dispose()


def register(
    client: TestClient,
    email: str,
    *,
    password: str = "research-passphrase",
) -> dict[str, object]:
    response = client.post(
        "/api/session/register",
        headers={"Idempotency-Key": str(uuid4())},
        json={"email": email, "password": password},
    )
    assert response.status_code == 201, response.text
    return response.json()


def login(
    client: TestClient,
    email: str,
    *,
    password: str = "research-passphrase",
) -> dict[str, object]:
    response = client.post(
        "/api/session/login",
        headers={"Idempotency-Key": str(uuid4())},
        json={"email": email, "password": password},
    )
    assert response.status_code == 200, response.text
    return response.json()


def login_admin(client: TestClient) -> dict[str, object]:
    return login(client, TEST_ADMIN_EMAIL, password=TEST_ADMIN_PASSWORD)


def test_public_registration_never_grants_administrator_role(
    client: TestClient,
) -> None:
    register(client, "owner@example.com")
    assert client.get("/api/account").json()["role"] == "member"
    assert client.get("/api/admin/users").status_code == 403

    register(client, "member@example.com")
    assert client.get("/api/admin/users").status_code == 403

    client.cookies.clear()
    login_admin(client)
    directory = client.get("/api/admin/users")

    assert directory.status_code == 200
    assert directory.json()["total"] == 3
    assert {item["email"] for item in directory.json()["items"]} == {
        TEST_ADMIN_EMAIL,
        "member@example.com",
        "owner@example.com",
    }


def test_registration_grants_a_visible_credit_balance_and_ledger_entry(
    client: TestClient,
) -> None:
    register(client, "credits@example.com")

    response = client.get("/api/account/credits")

    assert response.status_code == 200
    payload = response.json()
    assert payload["is_unlimited"] is False
    assert payload["balance"] == 10000
    assert payload["credit_limit"] == 10000
    assert payload["grant_amount"] == 10000
    assert payload["pricing"] == {
        "input_tokens_per_credit": 100,
        "output_tokens_per_credit": 25,
    }
    assert payload["entries"] == []
    assert payload["total_entries"] == 0


def test_provisioned_administrator_has_unlimited_credits(
    client: TestClient,
) -> None:
    signed_in = login_admin(client)
    user_id = UUID(str(signed_in["user"]["user_id"]))

    response = client.get("/api/account/credits")

    assert response.status_code == 200
    assert response.json()["is_unlimited"] is True
    with client.app.state.credit_service_scope() as credits:
        before = credits.summary(user_id=user_id)
        run_id = uuid4()
        credits.ensure_can_start(user_id=user_id)
        credits.reserve(user_id=user_id, run_id=run_id)
        charged = credits.charge(
            user_id=user_id,
            run_id=run_id,
            input_tokens=1_000_000,
            output_tokens=1_000_000,
            model="internal-runtime",
        )
        after = credits.summary(user_id=user_id)

    assert charged is None
    assert after.is_unlimited is True
    assert after.balance == before.balance
    assert after.entries == before.entries


def test_credit_reservation_fallback_uses_the_current_welcome_grant(
    client: TestClient,
) -> None:
    registered = register(client, "reserve-fallback@example.com")
    user_id = UUID(str(registered["user"]["user_id"]))

    with client.app.state.database.session() as session:
        repository = SqliteCreditRepository(session)
        repository.reserve_usage(
            user_id=user_id,
            run_id=uuid4(),
            now=datetime.now(UTC),
        )
        summary = repository.get_summary(user_id=user_id, limit=10)

    assert summary is not None
    assert summary.balance == 10000


def test_new_credit_reservation_preempts_an_abandoned_agent_run(
    client: TestClient,
) -> None:
    registered = register(client, "reserve-preemption@example.com")
    user_id = UUID(str(registered["user"]["user_id"]))
    abandoned_run_id = uuid4()
    replacement_run_id = uuid4()

    with client.app.state.database.session() as session:
        repository = SqliteCreditRepository(session)
        repository.reserve_usage(
            user_id=user_id,
            run_id=abandoned_run_id,
            now=datetime.now(UTC),
        )
        repository.reserve_usage(
            user_id=user_id,
            run_id=replacement_run_id,
            now=datetime.now(UTC),
        )
        account = session.get(CreditAccountRow, str(user_id), populate_existing=True)

    assert account is not None
    assert account.active_run_id == str(replacement_run_id)


def test_credit_ledger_is_returned_in_non_overlapping_pages(
    client: TestClient,
) -> None:
    registered = register(client, "credit-pages@example.com")
    user_id = UUID(str(registered["user"]["user_id"]))
    with client.app.state.credit_service_scope() as credits:
        for _ in range(3):
            run_id = uuid4()
            credits.reserve(user_id=user_id, run_id=run_id)
            credits.charge(
                user_id=user_id,
                run_id=run_id,
                input_tokens=100,
                output_tokens=25,
                model="internal-runtime",
            )

    first = client.get("/api/account/credits", params={"limit": 2})
    second = client.get(
        "/api/account/credits",
        params={"limit": 2, "cursor": first.json()["next_cursor"]},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["total_entries"] == 3
    assert first.json()["next_cursor"] == "2"
    assert second.json()["next_cursor"] is None
    first_ids = {entry["entry_id"] for entry in first.json()["entries"]}
    second_ids = {entry["entry_id"] for entry in second.json()["entries"]}
    assert len(first_ids) == 2
    assert len(second_ids) == 1
    assert first_ids.isdisjoint(second_ids)


def test_administrator_generates_hashed_codes_and_member_redeems_once(
    client: TestClient,
) -> None:
    login_admin(client)
    batch_key = str(uuid4())
    generated = client.post(
        "/api/admin/credit-redemption-codes",
        headers={"Idempotency-Key": batch_key},
        json={"count": 2, "expires_in_days": 7},
    )

    assert generated.status_code == 201
    payload = generated.json()
    assert payload["points"] == 10000
    assert len(payload["codes"]) == len(set(payload["codes"])) == 2
    assert all(code.startswith("QX-") and len(code) == 22 for code in payload["codes"])

    replay = client.post(
        "/api/admin/credit-redemption-codes",
        headers={"Idempotency-Key": batch_key},
        json={"count": 2, "expires_in_days": 7},
    )
    assert replay.status_code == 201
    assert replay.json()["codes"] == payload["codes"]

    with client.app.state.database.engine.connect() as connection:
        stored_hashes = connection.execute(
            text("SELECT code_hash FROM credit_redemption_codes")
        ).scalars().all()
    assert len(stored_hashes) == 2
    assert not set(payload["codes"]) & set(stored_hashes)

    client.cookies.clear()
    redeemer = register(client, "redeemer@example.com")
    redeemer_user_id = str(redeemer["user"]["user_id"])
    with client.app.state.database.engine.begin() as connection:
        connection.execute(
            text("UPDATE credit_accounts SET balance = 1200 WHERE user_id = :user_id"),
            {"user_id": redeemer_user_id},
        )
    redeemed = client.post(
        "/api/account/credit-redemptions",
        headers={"Idempotency-Key": str(uuid4())},
        json={"code": payload["codes"][0].lower()},
    )
    with client.app.state.database.engine.begin() as connection:
        connection.execute(
            text("UPDATE credit_accounts SET balance = 2936 WHERE user_id = :user_id"),
            {"user_id": redeemer_user_id},
        )
    replayed_redemption = client.post(
        "/api/account/credit-redemptions",
        headers={"Idempotency-Key": str(uuid4())},
        json={"code": payload["codes"][0]},
    )

    assert redeemed.status_code == 200
    assert redeemed.json() == {"redeemed_points": 10000, "balance": 10000}
    assert replayed_redemption.status_code == 200
    assert replayed_redemption.json() == {"redeemed_points": 10000, "balance": 2936}
    summary = client.get("/api/account/credits").json()
    assert summary["balance"] == 2936
    assert summary["credit_limit"] == 10000
    assert summary["entries"] == []
    with client.app.state.database.engine.connect() as connection:
        redemption_entry = connection.execute(
            text(
                "SELECT kind, points FROM credit_ledger "
                "WHERE user_id = :user_id AND kind = 'redemption'"
            ),
            {"user_id": redeemer_user_id},
        ).one()
    assert redemption_entry == ("redemption", 10000)

    client.cookies.clear()
    register(client, "other-redeemer@example.com")
    unavailable = client.post(
        "/api/account/credit-redemptions",
        headers={"Idempotency-Key": str(uuid4())},
        json={"code": payload["codes"][0]},
    )
    assert unavailable.status_code == 409
    assert unavailable.json()["error"]["code"] == "credit_code_unavailable"


def test_member_cannot_generate_credit_redemption_codes(
    client: TestClient,
) -> None:
    register(client, "member-generator@example.com")

    response = client.post(
        "/api/admin/credit-redemption-codes",
        headers={"Idempotency-Key": str(uuid4())},
        json={"count": 1, "expires_in_days": 7},
    )

    assert response.status_code == 403


def test_concurrent_clean_registration_never_grants_administrator_role(
    client: TestClient,
) -> None:
    barrier = Barrier(2)

    def create(email: str) -> tuple[int, str]:
        with TestClient(client.app) as contender:
            barrier.wait(timeout=5)
            response = contender.post(
                "/api/session/register",
                headers={"Idempotency-Key": str(uuid4())},
                json={"email": email, "password": "research-passphrase"},
            )
            role = contender.get("/api/account").json()["role"]
            return response.status_code, role

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                create,
                ["first-contender@example.com", "second-contender@example.com"],
            )
        )

    assert [status for status, _role in results] == [201, 201]
    assert [role for _status, role in results] == ["member", "member"]


def test_install_provisions_the_fixed_admin_without_database_or_cli_work(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    alembic_config: Config,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'legacy-bootstrap.db'}"
    monkeypatch.setenv("QUNXUE_DATABASE_URL", database_url)
    command.upgrade(alembic_config, "20260820_0005")
    password_hasher = Argon2PasswordHasher()
    now = datetime.now(UTC)
    database = Database(database_url)
    with database.engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO users (
                    user_id, email, password_hash, display_name, created_at, updated_at
                ) VALUES (
                    :user_id, :email, :password_hash, :display_name, :created_at, :updated_at
                )
                """
            ),
            {
                "user_id": str(uuid4()),
                "email": "legacy-owner@example.com",
                "password_hash": password_hasher.hash("legacy-passphrase"),
                "display_name": "旧数据负责人",
                "created_at": now,
                "updated_at": now,
            },
        )
    command.upgrade(alembic_config, "head")
    settings = Settings(
        _env_file=None,
        database_url=database_url,
        runtime_mode="mock",
        model_base_url=None,
        model_api_key=None,
        model_name=None,
        model_extra_headers={},
        model_sft_resource_id=None,
    )
    app = create_app(settings=settings, database=database)
    install_account_management(
        app,
        database=database,
        password_hasher=password_hasher,
        initial_admin_email=TEST_ADMIN_EMAIL,
        initial_admin_password=TEST_ADMIN_PASSWORD,
    )

    try:
        with TestClient(app) as administrator:
            login_admin(administrator)
            account = administrator.get("/api/account")
            assert account.status_code == 200
            assert account.json()["email"] == TEST_ADMIN_EMAIL
            assert account.json()["role"] == "admin"
            assert account.json()["is_protected_admin"] is True
            assert administrator.get("/api/account/admin-bootstrap").status_code == 404
            directory = administrator.get("/api/admin/users").json()["items"]
            assert {item["email"] for item in directory} == {
                TEST_ADMIN_EMAIL,
                "legacy-owner@example.com",
            }
            provisioned = next(
                item for item in directory if item["email"] == TEST_ADMIN_EMAIL
            )
            assert provisioned["is_protected_admin"] is True
            audit = administrator.get("/api/admin/audit-events").json()["items"]
            assert any(event["action"] == "admin.provisioned" for event in audit)
            assert TEST_ADMIN_PASSWORD not in json.dumps(audit)
    finally:
        database.engine.dispose()


def test_profile_preferences_and_model_authorization_persist_with_real_replay(
    client: TestClient,
) -> None:
    register(client, "profile@example.com")
    account = client.get("/api/account")
    assert account.status_code == 200
    assert account.json()["preferences"] == {
        "locale": "zh-CN",
        "timezone": "Asia/Shanghai",
        "research_updates_enabled": True,
        "model_improvement_allowed": False,
        "consent_policy_version": "2026-08-secondary-use-v1",
        "consent_updated_at": None,
        "version": 1,
    }

    profile_key = str(uuid4())
    profile_payload = {
        "display_name": "  林同学  ",
        "expected_version": account.json()["version"],
    }
    updated = client.patch(
        "/api/account/profile",
        headers={"Idempotency-Key": profile_key},
        json=profile_payload,
    )
    replayed = client.patch(
        "/api/account/profile",
        headers={"Idempotency-Key": profile_key},
        json=profile_payload,
    )
    conflict = client.patch(
        "/api/account/profile",
        headers={"Idempotency-Key": profile_key},
        json={"display_name": "另一个名字", "expected_version": 1},
    )

    assert updated.status_code == replayed.status_code == 200
    assert updated.json() == replayed.json()
    assert updated.json()["display_name"] == "林同学"
    assert updated.json()["version"] == 2
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "idempotency_conflict"

    preference = client.patch(
        "/api/account/preferences",
        headers={"Idempotency-Key": str(uuid4())},
        json={
            "locale": "zh-CN",
            "timezone": "Asia/Shanghai",
            "research_updates_enabled": False,
            "expected_version": 1,
        },
    )
    authorization = client.patch(
        "/api/account/model-data-authorization",
        headers={"Idempotency-Key": str(uuid4())},
        json={
            "allowed": True,
            "policy_version": "2026-08-secondary-use-v1",
            "expected_version": preference.json()["version"],
        },
    )

    assert preference.status_code == 200
    assert authorization.status_code == 200
    assert authorization.json()["model_improvement_allowed"] is True
    restored = client.get("/api/account").json()
    assert restored["display_name"] == "林同学"
    assert restored["preferences"]["research_updates_enabled"] is False
    assert restored["preferences"]["model_improvement_allowed"] is True


def test_password_change_revokes_other_sessions_and_keeps_the_current_session(
    client: TestClient,
) -> None:
    register(client, "security@example.com")

    with TestClient(client.app) as other_device:
        login(other_device, "security@example.com")
        sessions = client.get("/api/account/sessions")
        assert sessions.status_code == 200
        assert len(sessions.json()["items"]) == 2
        assert sum(item["current"] for item in sessions.json()["items"]) == 1

        changed = client.post(
            "/api/account/password/change",
            headers={"Idempotency-Key": str(uuid4())},
            json={
                "current_password": "research-passphrase",
                "new_password": "new-research-passphrase",
                "revoke_other_sessions": True,
            },
        )

        assert changed.status_code == 200
        assert changed.json()["revoked_session_count"] == 1
        assert client.get("/api/session").status_code == 200
        assert other_device.get("/api/session").status_code == 401

    client.cookies.clear()
    rejected = client.post(
        "/api/session/login",
        headers={"Idempotency-Key": str(uuid4())},
        json={"email": "security@example.com", "password": "research-passphrase"},
    )
    assert rejected.status_code == 401
    login(client, "security@example.com", password="new-research-passphrase")


def test_admin_disable_enable_and_password_reset_are_real_lifecycle_actions(
    client: TestClient,
) -> None:
    login_admin(client)

    with TestClient(client.app) as managed_user:
        registered = register(
            managed_user,
            "managed-user@example.com",
            password="member-passphrase",
        )
        user_id = registered["user"]["user_id"]
        user = next(
            item
            for item in client.get("/api/admin/users?query=managed-user").json()["items"]
            if item["user_id"] == user_id
        )
        disabled = client.post(
            f"/api/admin/users/{user_id}/disable",
            headers={"Idempotency-Key": str(uuid4())},
            json={"expected_version": user["version"], "reason": "内测资格暂停"},
        )
        assert disabled.status_code == 200
        assert disabled.json()["status"] == "disabled"
        assert managed_user.get("/api/session").status_code == 401

        enabled = client.post(
            f"/api/admin/users/{user_id}/enable",
            headers={"Idempotency-Key": str(uuid4())},
            json={
                "expected_version": disabled.json()["version"],
                "reason": "恢复内测资格",
            },
        )
        assert enabled.status_code == 200
        assert enabled.json()["status"] == "active"
        login(managed_user, "managed-user@example.com", password="member-passphrase")

        reset_key = str(uuid4())
        reset = client.post(
            f"/api/admin/users/{user_id}/password-reset-links",
            headers={"Idempotency-Key": reset_key},
        )
        replayed_reset = client.post(
            f"/api/admin/users/{user_id}/password-reset-links",
            headers={"Idempotency-Key": reset_key},
        )
        assert reset.status_code == replayed_reset.status_code == 201
        assert reset.json() == replayed_reset.json()
        reset_token = reset.json()["reset_token"]
        assert reset_token
        managed_user.cookies.clear()
        consumed = managed_user.post(
            "/api/account/password-resets/consume",
            headers={"Idempotency-Key": str(uuid4())},
            json={"token": reset_token, "new_password": "reset-research-passphrase"},
        )
        assert consumed.status_code == 200
        reused = managed_user.post(
            "/api/account/password-resets/consume",
            headers={"Idempotency-Key": str(uuid4())},
            json={"token": reset_token, "new_password": "another-passphrase"},
        )
        assert reused.status_code == 410
        login(managed_user, "managed-user@example.com", password="reset-research-passphrase")

    audit = client.get("/api/admin/audit-events")
    assert audit.status_code == 200
    actions = {event["action"] for event in audit.json()["items"]}
    assert {
        "user.disabled",
        "user.enabled",
        "password_reset.issued",
        "password_reset.consumed",
    } <= actions


def test_provisioned_administrator_is_protected_and_denials_are_audited(
    client: TestClient,
) -> None:
    login_admin(client)
    account = client.get("/api/account").json()
    user_id = account["user_id"]
    with TestClient(client.app) as second_admin:
        registered = register(second_admin, "second-admin@example.com")
    second_user_id = registered["user"]["user_id"]
    second_user = next(
        item
        for item in client.get("/api/admin/users?query=second-admin").json()["items"]
        if item["user_id"] == second_user_id
    )
    promoted = client.patch(
        f"/api/admin/users/{second_user_id}/role",
        headers={"Idempotency-Key": str(uuid4())},
        json={
            "role": "admin",
            "expected_version": second_user["version"],
            "reason": "验证部署管理员保护",
        },
    )
    assert promoted.status_code == 200

    demoted = client.patch(
        f"/api/admin/users/{user_id}/role",
        headers={"Idempotency-Key": str(uuid4())},
        json={
            "role": "member",
            "expected_version": account["version"],
            "reason": "错误操作测试",
        },
    )
    disabled = client.post(
        f"/api/admin/users/{user_id}/disable",
        headers={"Idempotency-Key": str(uuid4())},
        json={"expected_version": account["version"], "reason": "错误操作测试"},
    )
    deactivated = client.post(
        "/api/account/deactivate",
        headers={"Idempotency-Key": str(uuid4())},
        json={
            "current_password": TEST_ADMIN_PASSWORD,
            "reason": "错误操作测试",
        },
    )
    deleted = client.post(
        "/api/account/delete",
        headers={"Idempotency-Key": str(uuid4())},
        json={
            "current_password": TEST_ADMIN_PASSWORD,
            "confirmation_email": TEST_ADMIN_EMAIL,
        },
    )

    assert {response.status_code for response in (demoted, disabled, deactivated, deleted)} == {
        409
    }
    assert {
        response.json()["error"]["code"]
        for response in (demoted, disabled, deactivated, deleted)
    } == {"provisioned_administrator_protected"}
    assert client.get("/api/session").status_code == 200
    outcomes = {
        (event["action"], event["outcome"])
        for event in client.get("/api/admin/audit-events").json()["items"]
    }
    assert {
        ("user.role_changed", "denied"),
        ("user.disabled", "denied"),
        ("account.deactivated", "denied"),
        ("account.deleted", "denied"),
    } <= outcomes


def test_sensitive_mutation_payload_changes_conflict_instead_of_replaying(
    client: TestClient,
) -> None:
    register(client, "password-replay@example.com")
    key = str(uuid4())
    changed = client.post(
        "/api/account/password/change",
        headers={"Idempotency-Key": key},
        json={
            "current_password": "research-passphrase",
            "new_password": "first-new-passphrase",
            "revoke_other_sessions": True,
        },
    )
    mismatched_replay = client.post(
        "/api/account/password/change",
        headers={"Idempotency-Key": key},
        json={
            "current_password": "research-passphrase",
            "new_password": "second-new-passphrase",
            "revoke_other_sessions": True,
        },
    )

    assert changed.status_code == 200
    assert mismatched_replay.status_code == 409
    assert mismatched_replay.json()["error"]["code"] == "idempotency_conflict"


def test_installed_account_contract_requires_idempotency_on_every_mutation(
    client: TestClient,
) -> None:
    schema = client.app.openapi()
    account_paths = {
        path: item
        for path, item in schema["paths"].items()
        if path.startswith("/api/account") or path.startswith("/api/admin")
    }
    assert {
        "/api/account",
        "/api/account/sessions",
        "/api/account/data-exports",
        "/api/admin/users",
        "/api/admin/audit-events",
    } <= set(account_paths)
    for path, path_item in account_paths.items():
        for method in ("post", "patch", "put", "delete"):
            operation = path_item.get(method)
            if operation is None:
                continue
            headers = {
                parameter["name"]: parameter
                for parameter in operation.get("parameters", [])
                if parameter["in"] == "header"
            }
            assert headers["Idempotency-Key"]["required"] is True, (
                f"{method.upper()} {path} has no required Idempotency-Key"
            )


def test_export_excludes_credentials_and_permanent_delete_purges_model_data(
    client: TestClient,
) -> None:
    login_admin(client)

    with TestClient(client.app) as deleting_user:
        registered = register(
            deleting_user,
            "delete-me@example.com",
            password="member-passphrase",
        )
        deleting_user_id = registered["user"]["user_id"]
        directory_user = next(
            item
            for item in client.get("/api/admin/users?query=delete-me").json()["items"]
            if item["user_id"] == deleting_user_id
        )
        promoted = client.patch(
            f"/api/admin/users/{deleting_user_id}/role",
            headers={"Idempotency-Key": str(uuid4())},
            json={
                "role": "admin",
                "expected_version": directory_user["version"],
                "reason": "账户删除边界测试",
            },
        )
        assert promoted.status_code == 200
        task = deleting_user.post(
            "/api/research-tasks",
            headers={"Idempotency-Key": str(uuid4())},
            json={"entry_type": "direct_input"},
        )
        assert task.status_code == 201
        task_id = task.json()["task_id"]
        trace_id = str(uuid4())
        now = datetime.now(UTC)
        with client.app.state.database.session() as session:
            session.add(
                ModelInvocationRow(
                    trace_id=trace_id,
                    request_id=str(uuid4()),
                    task_id=task_id,
                    contract_version="test",
                    capability="phenomenon_extraction",
                    provider="test",
                    model_version="test",
                    capability_tier="base",
                    demonstration=False,
                    scenario="default",
                    input_evidence={"private": "input"},
                    output={"private": "output"},
                    knowledge_release_id=None,
                    degraded=False,
                    degradation_reason=None,
                    error_code=None,
                    started_at=now,
                    completed_at=now,
                )
            )

        export_key = str(uuid4())
        created = deleting_user.post(
            "/api/account/data-exports",
            headers={"Idempotency-Key": export_key},
            json={"format": "json"},
        )
        replayed = deleting_user.post(
            "/api/account/data-exports",
            headers={"Idempotency-Key": export_key},
            json={"format": "json"},
        )
        assert created.status_code == replayed.status_code == 201
        assert created.json()["export_id"] == replayed.json()["export_id"]
        download = deleting_user.get(
            f"/api/account/data-exports/{created.json()['export_id']}/download"
        )
        assert download.status_code == 200
        assert download.headers["content-type"] == "application/json; charset=utf-8"
        assert download.headers["cache-control"] == "no-store"
        assert download.headers["content-disposition"] == (
            f'attachment; filename="qunxue-account-export-{created.json()["export_id"]}.json"'
        )
        payload = download.json()
        serialized = json.dumps(payload, ensure_ascii=False)
        assert task_id in serialized
        assert "private" in serialized
        assert "password_hash" not in serialized
        assert "credential_hash" not in serialized
        assert "token_digest" not in serialized
        assert "member-passphrase" not in serialized

        denied = deleting_user.post(
            "/api/account/delete",
            headers={
                "Idempotency-Key": str(uuid4()),
                "User-Agent": "Deletion audit browser",
            },
            json={
                "current_password": "incorrect-passphrase",
                "confirmation_email": "delete-me@example.com",
            },
        )
        assert denied.status_code == 401
        deleted = deleting_user.post(
            "/api/account/delete",
            headers={"Idempotency-Key": str(uuid4())},
            json={
                "current_password": "member-passphrase",
                "confirmation_email": "delete-me@example.com",
            },
        )
        assert deleted.status_code == 200
        assert deleted.json()["recoverable"] is False
        assert deleting_user.get("/api/session").status_code == 401

    with client.app.state.database.session() as session:
        assert session.get(UserRow, deleting_user_id) is None
        assert session.get(ResearchTaskRow, task_id) is None
        assert session.get(ModelInvocationRow, trace_id) is None
        assert session.scalar(select(func.count()).select_from(UserRow)) == 1
        deleted_user_audits = session.scalars(
            select(AccountAuditEventRow).where(
                AccountAuditEventRow.action == "account.deleted"
            )
        ).all()
        assert deleted_user_audits
        assert all(event.actor_email == "[deleted]" for event in deleted_user_audits)
        assert all(event.target_email == "[deleted]" for event in deleted_user_audits)
        assert all(event.ip_address is None for event in deleted_user_audits)
        assert all(event.user_agent is None for event in deleted_user_audits)


def test_export_includes_audit_rows_where_the_user_is_the_target_not_the_actor(
    client: TestClient,
) -> None:
    login_admin(client)
    with TestClient(client.app) as registering_member:
        registered = register(
            registering_member,
            "audit-target@example.com",
            password="member-passphrase",
        )
    member_id = registered["user"]["user_id"]
    reset = client.post(
        f"/api/admin/users/{member_id}/password-reset-links",
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert reset.status_code == 201

    with TestClient(client.app) as member_client:
        login(member_client, "audit-target@example.com", password="member-passphrase")
        created = member_client.post(
            "/api/account/data-exports",
            headers={"Idempotency-Key": str(uuid4())},
            json={"format": "json"},
        )
        payload = member_client.get(
            f"/api/account/data-exports/{created.json()['export_id']}/download"
        ).json()

    serialized = json.dumps(payload, ensure_ascii=False)
    assert "password_reset.issued" in serialized
    assert reset.json()["reset_token"] not in serialized
