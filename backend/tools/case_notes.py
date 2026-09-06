import json

from strands import tool

from backend.services.note_store import NoteStore, default_case_notes_path

_store: NoteStore | None = None


def set_tool_store(store: NoteStore | None) -> None:
    global _store
    _store = store


def _get_store() -> NoteStore:
    if _store is None:
        set_tool_store(NoteStore(default_case_notes_path()))
    assert _store is not None
    return _store


@tool
def create_case_note(note: str, source: str = "user", category: str = "general") -> str:
    """Store a structured note for the current RESOLVE case.

    Use this whenever the user provides case facts worth keeping - such as
    dates, claim numbers, parties, or developments - so they become part of
    the persisted case context.

    Args:
        note: The note text to store.
        source: Where the information came from (e.g. "user", "document", "company").
        category: Topic of the note (e.g. "warranty", "refund", "return", "general").

    Returns:
        A JSON string describing the stored note record.
    """
    if not note or not note.strip():
        return '{"status": "error", "message": "note must not be empty"}'
    try:
        record = _get_store().add(note=note.strip(), source=source, category=category)
    except Exception as exc:
        return json.dumps({"status": "error", "message": f"failed to persist note: {exc}"})
    return json.dumps({**record, "status": "stored"})