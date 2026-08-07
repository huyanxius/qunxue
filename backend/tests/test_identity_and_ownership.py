from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from qunxue_api.adapters.sqlite import UserRow


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
    assert response.status_code == 201
    return response.json()


def test_register_uses_an_http_only_cookie_and_hashes_the_password(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/session/register",
        headers={"Idempotency-Key": str(uuid4())},
        json={"email": "Researcher@Example.com", "password": "research-passphrase"},
    )

    assert response.status_code == 201
    assert response.json()["user"]["email"] == "researcher@example.com"
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert "research-passphrase" not in cookie
    assert "research-passphrase" not in response.text

    with client.app.state.database.session() as session:
        user = session.scalar(select(UserRow))
        assert user is not None
        assert user.password_hash != "research-passphrase"
        assert user.password_hash.startswith("$argon2")


def test_login_failure_does_not_reveal_whether_the_account_exists(
    client: TestClient,
) -> None:
    register(client, "known@example.com")
    client.cookies.clear()

    unknown = client.post(
        "/api/session/login",
        headers={"Idempotency-Key": str(uuid4())},
        json={"email": "unknown@example.com", "password": "wrong-password"},
    )
    wrong_password = client.post(
        "/api/session/login",
        headers={"Idempotency-Key": str(uuid4())},
        json={"email": "known@example.com", "password": "wrong-password"},
    )

    assert unknown.status_code == 401
    assert wrong_password.status_code == 401
    assert unknown.json()["error"]["code"] == "unauthenticated"
    assert wrong_password.json()["error"]["code"] == "unauthenticated"
    assert unknown.json()["error"]["message"] == wrong_password.json()["error"]["message"]


def test_registering_the_same_email_again_returns_a_stable_client_error(
    client: TestClient,
) -> None:
    register(client, "duplicate@example.com")
    client.cookies.clear()

    duplicate = client.post(
        "/api/session/register",
        headers={"Idempotency-Key": str(uuid4())},
        json={"email": "DUPLICATE@example.com", "password": "another-passphrase"},
    )

    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "validation_error"


def test_session_survives_a_refresh_and_logout_revokes_it(client: TestClient) -> None:
    registered = register(client, "session@example.com")

    current = client.get("/api/session")
    assert current.status_code == 200
    assert current.json()["session_id"] == registered["session_id"]

    logged_out = client.post(
        "/api/session/logout",
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert logged_out.status_code == 200
    assert logged_out.json()["status"] == "logged_out"
    assert client.get("/api/session").status_code == 401


def test_research_tasks_are_scoped_to_the_current_user_and_hard_deleted(
    client: TestClient,
) -> None:
    first_user = register(client, "first@example.com")
    created = client.post(
        "/api/research-tasks",
        headers={"Idempotency-Key": str(uuid4())},
        json={"entry_type": "direct_input"},
    )
    assert created.status_code == 201
    task_id = created.json()["task_id"]

    client.cookies.clear()
    register(client, "second@example.com")
    assert client.get(f"/api/research-tasks/{task_id}").status_code == 404
    assert client.post(
        f"/api/research-tasks/{task_id}/inputs/direct",
        headers={"Idempotency-Key": str(uuid4())},
        json={"phenomenon": "看不见的他人材料", "research_intent": None, "context": None},
    ).status_code == 404
    assert client.get("/api/research-tasks").json()["items"] == []

    client.cookies.clear()
    login = client.post(
        "/api/session/login",
        headers={"Idempotency-Key": str(uuid4())},
        json={"email": "first@example.com", "password": "research-passphrase"},
    )
    assert login.status_code == 200
    assert login.json()["user"]["user_id"] == first_user["user"]["user_id"]

    listed = client.get("/api/research-tasks")
    assert listed.status_code == 200
    assert [item["task_id"] for item in listed.json()["items"]] == [task_id]

    deleted = client.delete(
        f"/api/research-tasks/{task_id}",
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True
    assert client.get(f"/api/research-tasks/{task_id}").status_code == 404


def test_protected_research_endpoints_require_a_session(client: TestClient) -> None:
    task_id = uuid4()

    response = client.get(f"/api/research-tasks/{task_id}")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"
