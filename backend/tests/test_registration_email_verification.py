from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update

from qunxue_api.adapters.sqlite import (
    ModelInvocationRow,
    RegistrationVerificationRow,
    UserSessionRow,
)
from qunxue_api.adapters.sqlite.account_management_repository import SqliteAccountRepository
from qunxue_api.modules.account_management import service as account_service
from qunxue_api.modules.identity import service as identity_service


class RecordingEmailProvider:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    def send_verification_code(self, email: str, code: str) -> None:
        self.messages.append((email, code))


@pytest.fixture
def request_clock(monkeypatch):
    now = [datetime(2026, 10, 1, tzinfo=UTC)]
    clock = SimpleNamespace(now=lambda _tz: now[0])
    monkeypatch.setattr(account_service, "datetime", clock)
    monkeypatch.setattr(identity_service, "datetime", clock)
    return now


@pytest.mark.parametrize("scope", ["global", "client", "email"])
@pytest.mark.parametrize("endpoint,accepted,denied", [
    ("login", 200, 401),
    ("registration-code", 202, 429),
])
def test_public_session_rate_gates_reject_and_recover(
    plain_client, monkeypatch, request_clock, scope, endpoint, accepted, denied,
):
    client = plain_client
    provider = RecordingEmailProvider()
    client.app.state.email_provider = provider
    email = "gate@example.com"
    password = "research-passphrase"
    assert client.post(
        "/api/session/register", headers={"Idempotency-Key": str(uuid4())},
        json={"email": email, "password": password},
    ).status_code == 201
    reserve = SqliteAccountRepository._reserve_password_reset_request

    def test_threshold(repository, *, scope_key, limit, **kwargs):
        if scope_key.split(":")[1] == scope:
            limit = 2
        return reserve(repository, scope_key=scope_key, limit=limit, **kwargs)

    monkeypatch.setattr(
        SqliteAccountRepository, "_reserve_password_reset_request", test_threshold,
    )

    def request():
        return client.post(
            f"/api/session/{endpoint}", headers={"Idempotency-Key": str(uuid4())},
            json={"email": email, "password": password} if endpoint == "login"
            else {"email": email},
        )

    started = request_clock[0]
    responses = []
    for minute in range(3):
        request_clock[0] = started + timedelta(minutes=minute)
        responses.append(request())
    assert [response.status_code for response in responses] == [accepted, accepted, denied]
    assert "set-cookie" not in responses[-1].headers
    assert len(provider.messages) == (2 if endpoint == "registration-code" else 0)
    with client.app.state.database.session() as session:
        assert session.scalar(select(func.count()).select_from(UserSessionRow)) == (
            3 if endpoint == "login" else 1
        )
        assert session.scalar(select(func.count()).select_from(ModelInvocationRow)) == 0
    request_clock[0] = started + timedelta(hours=1)
    assert request().status_code == accepted
    assert len(provider.messages) == (3 if endpoint == "registration-code" else 0)


def test_login_gate_keeps_failed_attempts_and_existing_cooldown(plain_client, request_clock):
    client = plain_client
    email = "login-gate@example.com"
    password = "research-passphrase"
    assert client.post(
        "/api/session/register", headers={"Idempotency-Key": str(uuid4())},
        json={"email": email, "password": password},
    ).status_code == 201

    def login(password=password):
        return client.post(
            "/api/session/login", headers={"Idempotency-Key": str(uuid4())},
            json={"email": email, "password": password},
        )

    started = request_clock[0]
    assert login("wrong-password").status_code == 401
    assert login().status_code == 401
    request_clock[0] = started + timedelta(seconds=59)
    assert login().status_code == 401
    for minute in range(1, 5):
        request_clock[0] = started + timedelta(minutes=minute)
        assert login().status_code == 200
    request_clock[0] = started + timedelta(minutes=5)
    assert login().status_code == 401
    request_clock[0] = started + timedelta(hours=1)
    assert login().status_code == 200


def _send_code(client: TestClient, provider: RecordingEmailProvider, email: str) -> str:
    client.app.state.require_email_verification = True
    client.app.state.email_provider = provider
    response = client.post(
        "/api/session/registration-code",
        headers={"Idempotency-Key": str(uuid4())},
        json={"email": email},
    )
    assert response.status_code == 202
    assert response.json() == {
        "status": "accepted",
        "expires_in_seconds": 300,
        "resend_after_seconds": 60,
    }
    assert len(provider.messages) == 1
    return provider.messages[0][1]


def test_registration_requires_a_valid_email_code(client: TestClient) -> None:
    client.app.state.require_email_verification = True
    response = client.post(
        "/api/session/register",
        headers={"Idempotency-Key": str(uuid4())},
        json={"email": "unverified@example.com", "password": "research-passphrase"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["message"] == "验证码无效或已过期，请重新获取。"


def test_registration_code_is_delivered_and_consumed_once(client: TestClient) -> None:
    provider = RecordingEmailProvider()
    code = _send_code(client, provider, "Researcher@Example.com")

    registered = client.post(
        "/api/session/register",
        headers={"Idempotency-Key": str(uuid4())},
        json={
            "email": "researcher@example.com",
            "password": "research-passphrase",
            "verification_code": code,
        },
    )
    replayed = client.post(
        "/api/session/register",
        headers={"Idempotency-Key": str(uuid4())},
        json={
            "email": "another@example.com",
            "password": "research-passphrase",
            "verification_code": code,
        },
    )

    assert registered.status_code == 201
    assert registered.json()["user"]["email"] == "researcher@example.com"
    assert replayed.status_code == 422


def test_registration_code_rejects_immediate_resend(client: TestClient) -> None:
    provider = RecordingEmailProvider()
    _send_code(client, provider, "cooldown@example.com")

    response = client.post(
        "/api/session/registration-code",
        headers={"Idempotency-Key": str(uuid4())},
        json={"email": "cooldown@example.com"},
    )

    assert response.status_code == 429
    assert response.headers["retry-after"] == "60"
    assert len(provider.messages) == 1


def test_wrong_registration_code_never_creates_an_account(client: TestClient) -> None:
    provider = RecordingEmailProvider()
    _send_code(client, provider, "wrong-code@example.com")

    response = client.post(
        "/api/session/register",
        headers={"Idempotency-Key": str(uuid4())},
        json={
            "email": "wrong-code@example.com",
            "password": "research-passphrase",
            "verification_code": "000000",
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["message"] == "验证码无效或已过期，请重新获取。"


def test_registration_code_stops_working_after_five_wrong_attempts(client: TestClient) -> None:
    provider = RecordingEmailProvider()
    code = _send_code(client, provider, "attempt-limit@example.com")

    for _attempt in range(5):
        rejected = client.post(
            "/api/session/register",
            headers={"Idempotency-Key": str(uuid4())},
            json={
                "email": "attempt-limit@example.com",
                "password": "research-passphrase",
                "verification_code": "000000",
            },
        )
        assert rejected.status_code == 422

    exhausted = client.post(
        "/api/session/register",
        headers={"Idempotency-Key": str(uuid4())},
        json={
            "email": "attempt-limit@example.com",
            "password": "research-passphrase",
            "verification_code": code,
        },
    )

    assert exhausted.status_code == 422


def test_registration_code_is_hashed_and_expires_after_five_minutes(
    client: TestClient,
) -> None:
    provider = RecordingEmailProvider()
    code = _send_code(client, provider, "expiring@example.com")
    with client.app.state.database.session() as session:
        verification = session.scalar(select(RegistrationVerificationRow))
        assert verification is not None
        assert verification.code_hash != code
        assert verification.code_hash.startswith("$argon2")
        session.execute(
            update(RegistrationVerificationRow)
            .where(RegistrationVerificationRow.email == "expiring@example.com")
            .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )

    response = client.post(
        "/api/session/register",
        headers={"Idempotency-Key": str(uuid4())},
        json={
            "email": "expiring@example.com",
            "password": "research-passphrase",
            "verification_code": code,
        },
    )

    assert response.status_code == 422
