import json

import pytest

from backend.services.note_store import NoteStore
from backend.tools.case_notes import create_case_note, set_tool_store


@pytest.fixture
def note_store(tmp_path):
    store = NoteStore(tmp_path / "notes.json")
    set_tool_store(store)
    yield store
    set_tool_store(None)


def test_create_case_note_persists(note_store):
    result = create_case_note(
        note="Warranty claim rejected on 2026-01-05; damage said not covered.",
        source="user",
        category="warranty",
    )
    assert note_store.count() == 1

    record = json.loads(result)
    assert record["status"] == "stored"
    assert record["id"]
    assert record["note"].startswith("Warranty claim rejected")
    assert record["source"] == "user"
    assert record["category"] == "warranty"
    assert record["created_at"]


def test_create_case_note_returns_meaningful_result(note_store):
    result = create_case_note(note="Refund of 349.99 expected.", source="company", category="refund")
    record = json.loads(result)
    assert record["status"] == "stored"
    assert record["category"] == "refund"
    assert record["source"] == "company"

    stored = note_store.list_all()
    assert stored[0]["note"] == "Refund of 349.99 expected."


def test_create_case_note_rejects_empty_note(note_store):
    result = create_case_note(note="   ")
    assert json.loads(result)["status"] == "error"
    assert note_store.count() == 0