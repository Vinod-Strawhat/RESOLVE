import pytest

from backend.services.conversation import load_session_history, to_agent_transcript
from backend.services.memory_store import MemoryStore


def test_to_agent_transcript_shapes_messages():
    messages = [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "reply"},
    ]
    transcript = to_agent_transcript(messages)
    assert transcript == [
        {"role": "user", "content": [{"text": "first"}]},
        {"role": "assistant", "content": [{"text": "reply"}]},
    ]


def test_to_agent_transcript_preserves_order():
    messages = [
        {"role": "user", "content": "one"},
        {"role": "assistant", "content": "two"},
        {"role": "user", "content": "three"},
    ]
    roles = [item["role"] for item in to_agent_transcript(messages)]
    assert roles == ["user", "assistant", "user"]


def test_to_agent_transcript_empty():
    assert to_agent_transcript([]) == []


def test_load_session_history_requires_store(tmp_path):
    store = MemoryStore(tmp_path / "resolve.db")
    session_id = store.create_session()
    store.save_message(session_id, "user", "first")
    store.save_message(session_id, "assistant", "reply")
    store.save_message(session_id, "user", "second")

    history = load_session_history(store, session_id)
    assert [m["role"] for m in history] == ["user", "assistant", "user"]
    assert [m["content"] for m in history] == ["first", "reply", "second"]


def test_load_session_history_unknown_session(tmp_path):
    store = MemoryStore(tmp_path / "resolve.db")
    assert load_session_history(store, "does-not-exist") == []


def test_load_session_history_applies_limit(tmp_path):
    store = MemoryStore(tmp_path / "resolve.db")
    session_id = store.create_session()
    for index in range(5):
        store.save_message(session_id, "user", f"message {index}")
    assert len(load_session_history(store, session_id, limit=2)) == 2