import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_MEMORY_DB_PATH = Path(__file__).resolve().parents[2] / "database" / "resolve.db"

VALID_ROLES = ("user", "assistant")


def default_memory_db_path() -> Path:
    configured = os.environ.get("MEMORY_DB_PATH")
    if configured:
        return Path(configured)
    return DEFAULT_MEMORY_DB_PATH


_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions (id)
);

CREATE INDEX IF NOT EXISTS idx_messages_session_created
    ON messages (session_id, created_at);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class MemoryStore:
    """SQLite-backed session and conversation-message storage."""

    def __init__(self, path: str | Path):
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _execute(self, sql: str, params: tuple = ()) -> None:
        with self._connect() as conn:
            conn.execute(sql, params)

    def create_session(self) -> str:
        session_id = uuid.uuid4().hex
        now = _now()
        self._execute(
            "INSERT INTO sessions (id, created_at, updated_at) VALUES (?, ?, ?)",
            (session_id, now, now),
        )
        return session_id

    def session_exists(self, session_id: str) -> bool:
        return self.get_session(session_id) is not None

    def get_session(self, session_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, created_at, updated_at FROM sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
        return dict(row) if row else None

    def touch_session(self, session_id: str) -> None:
        self._execute(
            "UPDATE sessions SET updated_at = ? WHERE id = ?",
            (_now(), session_id),
        )

    def save_message(self, session_id: str, role: str, content: str) -> dict:
        if role not in VALID_ROLES:
            raise ValueError(f"role must be one of {VALID_ROLES}, got {role!r}")
        message = {
            "id": uuid.uuid4().hex,
            "session_id": session_id,
            "role": role,
            "content": content,
            "created_at": _now(),
        }
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO messages (id, session_id, role, content, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (message["id"], session_id, role, content, message["created_at"]),
            )
            conn.execute(
                "UPDATE sessions SET updated_at = ? WHERE id = ?",
                (message["created_at"], session_id),
            )
        return message

    def list_messages(self, session_id: str, limit: int = 50) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, session_id, role, content, created_at FROM messages "
                "WHERE session_id = ? ORDER BY created_at, rowid LIMIT ?",
                (session_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]


_store: MemoryStore | None = None
_store_lock = threading.Lock()


def get_memory_store() -> MemoryStore:
    global _store
    with _store_lock:
        if _store is None:
            _store = MemoryStore(default_memory_db_path())
        return _store


def set_memory_store(store: MemoryStore | None) -> None:
    global _store
    with _store_lock:
        _store = store