import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_CASE_NOTES_PATH = Path(__file__).resolve().parents[2] / "database" / "case_notes.json"


def default_case_notes_path() -> Path:
    configured = os.environ.get("CASE_NOTES_PATH")
    if configured:
        return Path(configured)
    return DEFAULT_CASE_NOTES_PATH


class NoteStore:
    def __init__(self, path: str | Path):
        self._path = Path(path)
        self._lock = threading.Lock()

    def add(self, note: str, source: str, category: str) -> dict:
        record = {
            "id": uuid.uuid4().hex,
            "note": note,
            "source": source,
            "category": category,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        with self._lock:
            records = self._read()
            records.append(record)
            self._write(records)
        return record

    def list_all(self) -> list[dict]:
        with self._lock:
            return self._read()

    def count(self) -> int:
        return len(self.list_all())

    def _read(self) -> list[dict]:
        if not self._path.exists():
            return []
        with self._path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def _write(self, records: list[dict]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("w", encoding="utf-8") as f:
            json.dump(records, f, indent=2)