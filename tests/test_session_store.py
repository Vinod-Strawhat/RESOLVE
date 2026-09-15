import pytest

from backend.services.session_store import SessionStore


@pytest.fixture
def store(tmp_path):
    return SessionStore(tmp_path / "resolve.db")


@pytest.fixture
def user_store(tmp_path):
    from backend.services.user_store import UserStore

    return UserStore(tmp_path / "resolve.db")


def test_create_and_get_session(store, user_store):
    user = user_store.create_user(email="a@example.com", password_hash="$argon2$h")
    session = store.create_session(
        user_id=user["id"], token_hash="abc123", expires_at="2030-01-01T00:00:00+00:00"
    )
    assert session["user_id"] == user["id"]
    found = store.get_session("abc123")
    assert found is not None
    assert found["expires_at"] == "2030-01-01T00:00:00+00:00"


def test_get_session_unknown_hash_returns_none(store):
    assert store.get_session("does-not-exist") is None


def test_delete_session(store, user_store):
    user = user_store.create_user(email="a@example.com", password_hash="$argon2$h")
    store.create_session(user_id=user["id"], token_hash="abc123", expires_at="2030-01-01T00:00:00+00:00")
    assert store.delete_session("abc123") is True
    assert store.get_session("abc123") is None
    assert store.delete_session("abc123") is False


def test_delete_expired(store, user_store):
    user = user_store.create_user(email="a@example.com", password_hash="$argon2$h")
    store.create_session(user_id=user["id"], token_hash="old", expires_at="2020-01-01T00:00:00+00:00")
    store.create_session(user_id=user["id"], token_hash="new", expires_at="2030-01-01T00:00:00+00:00")
    removed = store.delete_expired("2025-01-01T00:00:00+00:00")
    assert removed == 1
    assert store.get_session("old") is None
    assert store.get_session("new") is not None


def test_token_hash_is_unique_primary_key(store, user_store):
    user = user_store.create_user(email="a@example.com", password_hash="$argon2$h")
    store.create_session(user_id=user["id"], token_hash="abc", expires_at="2030-01-01T00:00:00+00:00")
    with pytest.raises(Exception):
        store.create_session(user_id=user["id"], token_hash="abc", expires_at="2030-01-01T00:00:00+00:00")