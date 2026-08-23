from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select, update

from qunxue_api.adapters.sqlite import RegistrationVerificationRow


class RecordingEmailProvider:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    def send_verification_code(self, email: str, code: str) -> None:
        self.messages.append((email, code))


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
