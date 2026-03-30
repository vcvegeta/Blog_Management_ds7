from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import get_token

client = TestClient(app)


def test_login_success_returns_token():
    """Valid credentials → JWT token returned (200 OK)."""
    response = client.post(
        "/auth/login",
        data={"username": "alice", "password": "alice123"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"


def test_login_failure_wrong_password():
    """Invalid password → 401 Unauthorized."""
    response = client.post(
        "/auth/login",
        data={"username": "alice", "password": "wrongpassword"},
    )
    assert response.status_code == 401


def test_login_failure_wrong_username():
    """Non-existent user → 401 Unauthorized."""
    response = client.post(
        "/auth/login",
        data={"username": "nobody", "password": "password"},
    )
    assert response.status_code == 401


def test_users_me_without_token_returns_401():
    """GET /users/me without token → 401 Unauthorized."""
    response = client.get("/users/me")
    assert response.status_code == 401


def test_users_me_with_valid_token():
    """GET /users/me with valid token → 200 OK with user info."""
    token = get_token("alice", "alice123")
    response = client.get(
        "/users/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["username"] == "alice"
    assert body["role"] == "reader"
