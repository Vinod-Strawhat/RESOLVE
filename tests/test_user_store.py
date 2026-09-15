import pytest

from backend.services.user_store import DuplicateEmailError, UserStore


@pytest.fixture
def store(tmp_path):
    return UserStore(tmp_path / "resolve.db")


def test_create_and_get_user(store):
    user = store.create_user(
        email="alice@example.com", password_hash="$argon2$hash", display_name="Alice"
    )
    assert user["email"] == "alice@example.com"
    assert user["password_hash"] == "$argon2$hash"
    assert user["display_name"] == "Alice"
    assert user["created_at"]
    assert store.get_user(user["id"])["email"] == "alice@example.com"


def test_get_user_by_email(store):
    store.create_user(email="alice@example.com", password_hash="$argon2$hash")
    found = store.get_user_by_email("alice@example.com")
    assert found is not None
    assert found["email"] == "alice@example.com"
    assert store.get_user_by_email("nobody@example.com") is None


def test_duplicate_email_raises(store):
    store.create_user(email="alice@example.com", password_hash="$argon2$hash")
    with pytest.raises(DuplicateEmailError):
        store.create_user(email="alice@example.com", password_hash="$argon2$other")


def test_empty_email_and_hash_rejected(store):
    with pytest.raises(ValueError):
        store.create_user(email="", password_hash="$argon2$hash")
    with pytest.raises(ValueError):
        store.create_user(email="a@example.com", password_hash="")


def test_restart_persistence(tmp_path):
    path = tmp_path / "resolve.db"
    UserStore(path).create_user(email="alice@example.com", password_hash="$argon2$hash")
    reopened = UserStore(path)
    assert reopened.get_user_by_email("alice@example.com") is not None