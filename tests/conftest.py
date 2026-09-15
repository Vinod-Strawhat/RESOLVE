"""Shared Phase 8B test fixtures/helpers.

Provides deterministic helpers for creating test users, issuing auth
session tokens, and building cookie-authenticated ``TestClient`` instances
so endpoint tests exercise the real ``get_current_user`` dependency.
"""

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services.auth import (
    COOKIE_NAME,
    generate_session_token,
    get_session_expiry,
    hash_token,
)
from backend.services.session_store import SessionStore
from backend.services.user_store import UserStore

TEST_EMAIL = "test@example.com"
TEST_PASSWORD_HASH = "$argon2$test-hash-not-a-password"


def create_test_user(
    user_store: UserStore,
    email: str = TEST_EMAIL,
    display_name: str = "Test User",
) -> dict:
    """Create (or fetch) the canonical per-DB test user."""
    existing = user_store.get_user_by_email(email)
    if existing is not None:
        return existing
    return user_store.create_user(
        email=email,
        password_hash=TEST_PASSWORD_HASH,
        display_name=display_name,
    )


def issue_auth_token(session_store: SessionStore, user_id: str) -> str:
    """Create an auth session and return its raw cookie token."""
    token = generate_session_token()
    session_store.create_session(
        user_id=user_id,
        token_hash=hash_token(token),
        expires_at=get_session_expiry(),
    )
    return token


def auth_client(
    monkeypatch,
    db_path,
    user_store: UserStore,
    session_store: SessionStore,
    user_id: str,
) -> TestClient:
    """Wire the auth singletons to the test stores and return an authed client."""
    monkeypatch.setattr(
        "backend.api.dependencies.get_user_store", lambda: user_store
    )
    monkeypatch.setattr(
        "backend.api.dependencies.get_session_store", lambda: session_store
    )
    client = TestClient(app)
    client.cookies.set(
        COOKIE_NAME, issue_auth_token(session_store, user_id)
    )
    return client


@pytest.fixture
def user(tmp_path):
    """A user row in the per-test database (shared path with other stores)."""
    return create_test_user(UserStore(tmp_path / "resolve.db"))