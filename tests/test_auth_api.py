import sqlite3

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.api.dependencies import get_current_user
from backend.main import app
from backend.services import auth as auth_service
from backend.services.session_store import SessionStore
from backend.services.user_store import UserStore

SIGNUP = {"email": "alice@example.com", "password": "supersecret-pw", "display_name": "Alice"}


@pytest.fixture
def env(tmp_path, monkeypatch):
    db = tmp_path / "resolve.db"
    users = UserStore(db)
    sessions = SessionStore(db)
    monkeypatch.setattr("backend.api.auth.get_user_store", lambda: users)
    monkeypatch.setattr("backend.api.auth.get_session_store", lambda: sessions)
    monkeypatch.setattr("backend.api.dependencies.get_user_store", lambda: users)
    monkeypatch.setattr("backend.api.dependencies.get_session_store", lambda: sessions)
    return {"db": db, "users": users, "sessions": sessions}


@pytest.fixture
def client(env):
    return TestClient(app)


def _create_user(env, email="bob@example.com"):
    return env["users"].create_user(email=email, password_hash="$argon2$fixed-hash")


# ---------------------------------------------------------------- signup

def test_signup_success_returns_safe_user(client, env):
    response = client.post("/api/auth/signup", json=SIGNUP)
    assert response.status_code == 200
    body = response.json()["user"]
    assert body["email"] == "alice@example.com"
    assert body["display_name"] == "Alice"
    assert body["id"]
    assert body["created_at"]
    assert "password_hash" not in body


def test_signup_sets_cookie(client):
    response = client.post("/api/auth/signup", json=SIGNUP)
    assert "resolve_session" in client.cookies


def test_signup_stores_hashed_password_never_plaintext(client, env):
    client.post("/api/auth/signup", json=SIGNUP)
    user = env["users"].get_user_by_email("alice@example.com")
    assert user["password_hash"] != "supersecret-pw"
    assert "supersecret-pw" not in user["password_hash"]
    assert user["password_hash"].startswith("$argon2")


def test_signup_duplicate_email_409(client):
    first = client.post("/api/auth/signup", json=SIGNUP)
    assert first.status_code == 200
    second = client.post("/api/auth/signup", json={**SIGNUP, "email": "ALICE@Example.com "})
    assert second.status_code == 409


def test_signup_rejects_whitespace_password(client):
    response = client.post("/api/auth/signup", json={**SIGNUP, "password": "   "})
    assert response.status_code == 400
    assert "must not be empty" in response.json()["detail"]


def test_signup_rejects_blank_email(client):
    response = client.post("/api/auth/signup", json={**SIGNUP, "email": "   "})
    assert response.status_code == 400
    assert "invalid email" in response.json()["detail"]


def test_signup_normalizes_email(client):
    response = client.post(
        "/api/auth/signup", json={**SIGNUP, "email": "  Mixed.Case@Example.COM  "}
    )
    assert response.status_code == 200
    assert response.json()["user"]["email"] == "mixed.case@example.com"


def test_signup_missing_fields_422(client):
    assert client.post("/api/auth/signup", json={"email": "a@b.com"}).status_code == 422


# ---------------------------------------------------------------- login

def test_login_success(client):
    client.post("/api/auth/signup", json=SIGNUP)
    response = client.post("/api/auth/login", json=SIGNUP)
    assert response.status_code == 200
    body = response.json()["user"]
    assert body["email"] == "alice@example.com"
    assert "password_hash" not in response.json()


def test_login_wrong_password_401(client):
    client.post("/api/auth/signup", json=SIGNUP)
    response = client.post(
        "/api/auth/login", json={"email": "alice@example.com", "password": "wrong"}
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "invalid email or password"


def test_login_nonexistent_account_401_same_message(client):
    response = client.post(
        "/api/auth/login", json={"email": "ghost@example.com", "password": "whatever"}
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "invalid email or password"


def test_login_empty_credentials_401(client):
    response = client.post("/api/auth/login", json={"email": "a@b.com", "password": "  "})
    assert response.status_code == 401


def test_login_respects_normalized_email(client):
    client.post("/api/auth/signup", json=SIGNUP)
    response = client.post(
        "/api/auth/login",
        json={"email": "  ALICE@EXAMPLE.COM", "password": SIGNUP["password"]},
    )
    assert response.status_code == 200


# ---------------------------------------------------------------- me

def test_me_with_valid_session(client, env):
    client.post("/api/auth/signup", json=SIGNUP)
    response = client.get("/api/auth/me")
    assert response.status_code == 200
    user = response.json()["user"]
    assert user["email"] == "alice@example.com"
    assert "password_hash" not in response.text


def test_me_without_session_401(client):
    assert client.get("/api/auth/me").status_code == 401


def test_me_with_expired_session_401(client, env):
    token = auth_service.generate_session_token()
    user = _create_user(env)
    env["sessions"].create_session(
        user_id=user["id"],
        token_hash=auth_service.hash_token(token),
        expires_at="2020-01-01T00:00:00+00:00",
    )
    client.cookies.set("resolve_session", token)
    response = client.get("/api/auth/me")
    assert response.status_code == 401
    assert env["sessions"].get_session(auth_service.hash_token(token)) is None


# ---------------------------------------------------------------- logout

def test_logout_success(client):
    client.post("/api/auth/signup", json=SIGNUP)
    response = client.post("/api/auth/logout")
    assert response.status_code == 200
    assert response.json()["status"] == "logged_out"


def test_logout_invalidates_session(client, env):
    client.post("/api/auth/signup", json=SIGNUP)
    token = client.cookies.get("resolve_session")
    client.post("/api/auth/logout")
    assert env["sessions"].get_session(auth_service.hash_token(token)) is None
    assert client.get("/api/auth/me").status_code == 401


def test_logout_when_already_logged_out_is_safe(client):
    response = client.post("/api/auth/logout")
    assert response.status_code == 200


# ---------------------------------------------------------------- security properties

def test_session_token_never_stored_in_database(client, env):
    client.post("/api/auth/signup", json=SIGNUP)
    token = client.cookies.get("resolve_session")
    with sqlite3.connect(env["db"]) as conn:
        hashes = [
            row[0] for row in conn.execute("SELECT token_hash FROM auth_sessions")
        ]
    assert hashes
    for stored in hashes:
        assert stored != token
        assert token not in stored
        assert len(stored) == 64  # sha256 hex digest
    assert len(token) >= 43  # urlsafe b64 of >= 32 random bytes


def test_cookie_flags(client):
    response = client.post("/api/auth/signup", json=SIGNUP)
    set_cookie = response.headers["set-cookie"]
    assert "resolve_session=" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "samesite=strict" in set_cookie.lower()
    assert "Path=/" in set_cookie
    assert "Max-Age=2592000" in set_cookie  # 30 days
    assert "secure" not in set_cookie.lower()


def test_cookie_secure_flag_env_controlled(client, monkeypatch):
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "true")
    response = client.post("/api/auth/signup", json=SIGNUP)
    assert "Secure" in response.headers["set-cookie"]


def test_session_ttl_env_controlled(client, monkeypatch):
    monkeypatch.setenv("AUTH_SESSION_DAYS", "7")
    response = client.post("/api/auth/signup", json=SIGNUP)
    assert "Max-Age=604800" in response.headers["set-cookie"]


def test_user_isolation_between_accounts(env):
    client_a = TestClient(app)
    client_b = TestClient(app)
    client_a.post("/api/auth/signup", json=SIGNUP)
    client_b.post(
        "/api/auth/signup",
        json={"email": "carol@example.com", "password": "different-pw", "display_name": "Carol"},
    )
    user_a = client_a.get("/api/auth/me").json()["user"]
    user_b = client_b.get("/api/auth/me").json()["user"]
    assert user_a["email"] == "alice@example.com"
    assert user_b["email"] == "carol@example.com"
    session_a = client_a.cookies.get("resolve_session")
    session_b = client_b.cookies.get("resolve_session")
    assert auth_service.hash_token(session_a) != auth_service.hash_token(session_b)
    assert env["sessions"].get_session(auth_service.hash_token(session_a))["user_id"] == user_a["id"]
    assert env["sessions"].get_session(auth_service.hash_token(session_b))["user_id"] == user_b["id"]


# ---------------------------------------------------------------- dependency unit-level

def test_get_current_user_resolves_valid_session(env):
    user = _create_user(env)
    token = auth_service.generate_session_token()
    env["sessions"].create_session(
        user_id=user["id"],
        token_hash=auth_service.hash_token(token),
        expires_at="2030-01-01T00:00:00+00:00",
    )
    resolved = get_current_user(token)
    assert resolved["id"] == user["id"]


def test_get_current_user_rejects_missing_token(env):
    with pytest.raises(HTTPException) as excinfo:
        get_current_user(None)
    assert excinfo.value.status_code == 401


def test_get_current_user_rejects_unknown_token(env):
    with pytest.raises(HTTPException) as excinfo:
        get_current_user(auth_service.generate_session_token())
    assert excinfo.value.status_code == 401


def test_get_current_user_rejects_expired_session(env):
    user = _create_user(env)
    token = auth_service.generate_session_token()
    token_hash = auth_service.hash_token(token)
    env["sessions"].create_session(
        user_id=user["id"], token_hash=token_hash, expires_at="2020-01-01T00:00:00+00:00"
    )
    with pytest.raises(HTTPException) as excinfo:
        get_current_user(token)
    assert excinfo.value.status_code == 401
    assert env["sessions"].get_session(token_hash) is None