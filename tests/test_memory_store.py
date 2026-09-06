import time

import pytest

from backend.services.memory_store import MemoryStore, VALID_ROLES


@pytest.fixture
def store(tmp_path):
    return MemoryStore(tmp_path / "resolve.db")


def test_create_session_returns_collision_safe_id(store):
    session_id = store.create_session()
    assert len(session_id) == 32
    assert all(c in "0123456789abcdef" for c in session_id)
    assert store.session_exists(session_id)


def test_create_session_unique_ids(store):
    first = store.create_session()
    second = store.create_session()
    assert first != second


def test_get_session_returns_metadata(store):
    session_id = store.create_session()
    session = store.get_session(session_id)
    assert session["id"] == session_id
    assert session["created_at"]
    assert session["updated_at"]


def test_get_session_unknown_returns_none(store):
    assert store.get_session("missing") is None
    assert not store.session_exists("missing")


def test_save_and_list_messages_ordered(store):
    session_id = store.create_session()
    store.save_message(session_id, "user", "My laptop warranty claim was rejected.")
    time.sleep(0.01)
    store.save_message(session_id, "assistant", "I've recorded your case. Model?")
    time.sleep(0.01)
    store.save_message(session_id, "user", "It is an ASUS Vivobook.")

    messages = store.list_messages(session_id)
    assert [m["role"] for m in messages] == ["user", "assistant", "user"]
    assert [m["content"] for m in messages] == [
        "My laptop warranty claim was rejected.",
        "I've recorded your case. Model?",
        "It is an ASUS Vivobook.",
    ]
    for message in messages:
        assert message["id"]
        assert message["created_at"]


def test_messages_are_scoped_to_session(store):
    first = store.create_session()
    second = store.create_session()
    store.save_message(first, "user", "session-one message")
    assert len(store.list_messages(first)) == 1
    assert store.list_messages(second) == []


def test_list_messages_empty_session(store):
    assert store.list_messages(store.create_session()) == []


def test_list_messages_limit_applies(store):
    session_id = store.create_session()
    for index in range(5):
        store.save_message(session_id, "user", f"message {index}")
        time.sleep(0.01)
    assert len(store.list_messages(session_id, limit=3)) == 3
    assert store.list_messages(session_id, limit=3)[-1]["content"] == "message 2"


def test_save_message_rejects_unknown_role(store):
    session_id = store.create_session()
    with pytest.raises(ValueError, match="role"):
        store.save_message(session_id, "system", "hidden reasoning")


def test_save_message_to_missing_session_raises(store):
    with pytest.raises(Exception):
        store.save_message("missing-session", "user", "cannot attach")


def test_touch_session_updates_timestamp(store):
    session_id = store.create_session()
    original = store.get_session(session_id)["updated_at"]
    time.sleep(0.01)
    store.touch_session(session_id)
    assert store.get_session(session_id)["updated_at"] != original


def test_restart_persistence(tmp_path):
    path = tmp_path / "resolve.db"
    store_one = MemoryStore(path)
    session_id = store_one.create_session()
    store_one.save_message(session_id, "user", "Turn one persists.")
    time.sleep(0.01)
    store_one.save_message(session_id, "assistant", "Turn one replied.")
    expected = store_one.list_messages(session_id)
    del store_one

    store_two = MemoryStore(path)
    assert store_two.session_exists(session_id)
    assert store_two.list_messages(session_id) == expected


def test_schema_initialization_is_deterministic(tmp_path):
    path = tmp_path / "resolve.db"
    MemoryStore(path)
    MemoryStore(path)
    store = MemoryStore(path)
    session_id = store.create_session()
    store.save_message(session_id, "user", "still works")


def test_valid_roles():
    assert VALID_ROLES == ("user", "assistant")