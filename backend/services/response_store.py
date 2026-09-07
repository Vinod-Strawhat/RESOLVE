"""Persistent store for recorded/simulated support responses (Phase 6B).

A response represents a manually recorded or simulated reply from a support
side. Nothing here contacts an external service; the source is explicit so the
data clearly shows this is simulated/manual input for this phase.
"""

import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from backend.services.memory_store import default_memory_db_path

RESPONSES_DDL = """
CREATE TABLE IF NOT EXISTS responses (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    source TEXT NOT NULL,
    content TEXT NOT NULL,
    received_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (case_id) REFERENCES cases (id)
);

CREATE INDEX IF NOT EXISTS idx_responses_case_id ON responses (case_id);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_response_store_path() -> Path:
    configured = os.environ.get("MEMORY_DB_PATH")
    if configured:
        return Path(configured)
    return default_memory_db_path()


class ResponseStore:
    """SQLite-backed record of simulated/manual responses for a case."""

    def __init__(self, path: str | Path):
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(RESPONSES_DDL)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    _COLUMNS = ("id", "case_id", "source", "content", "received_at", "created_at")

    @classmethod
    def _row_to_response(cls, row: sqlite3.Row) -> dict:
        return {key: row[key] for key in cls._COLUMNS}

    def create_response(
        self, case_id: str, *, source: str, content: str
    ) -> dict:
        source = source.strip()
        content = content.strip()
        if not source:
            raise ValueError("response source must not be empty")
        if not content:
            raise ValueError("response content must not be empty")
        now = _now()
        response = {
            "id": uuid.uuid4().hex,
            "case_id": case_id,
            "source": source,
            "content": content,
            "received_at": now,
            "created_at": now,
        }
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO responses "
                "(id, case_id, source, content, received_at, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    response["id"],
                    case_id,
                    source,
                    content,
                    now,
                    now,
                ),
            )
        return response

    def get_response(self, response_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM responses WHERE id = ?", (response_id,)
            ).fetchone()
        return self._row_to_response(row) if row else None

    def list_responses_for_case(self, case_id: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM responses WHERE case_id = ? "
                "ORDER BY received_at, created_at, rowid",
                (case_id,),
            ).fetchall()
        return [self._row_to_response(row) for row in rows]


_response_store: ResponseStore | None = None
_response_store_lock = threading.Lock()


def get_response_store() -> ResponseStore:
    global _response_store
    with _response_store_lock:
        if _response_store is None:
            _response_store = ResponseStore(default_response_store_path())
        return _response_store


def set_response_store(store: ResponseStore | None) -> None:
    global _response_store
    with _response_store_lock:
        _response_store = store