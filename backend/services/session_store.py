"""Opaque authenticated-session persistence (Phase 8A).

Stores only ``sha256(token)`` in the ``auth_sessions`` table.  The raw
token lives exclusively in the client cookie and is never written to
SQLite or logs.
"""

import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from backend.services.memory_store import default_memory_db_path

AUTH_SESSIONS_DDL = """
CREATE TABLE IF NOT EXISTS auth_sessions (
    token_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users (id)
);

CREATE INDEX IF NOT EXISTS idx_auth_sessions_user_id ON auth_sessions (user_id);
"""

_SESSION_COLUMNS = ("token_hash", "user_id", "created_at", "expires_at")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_session_store_path() -> Path:
    configured = os.environ.get("MEMORY_DB_PATH")
    if configured:
        return Path(configured)
    return default_memory_db_path()


class SessionStore:
    """SQLite-backed authenticated session records.

    Sessions are keyed by the SHA-256 hash of the opaque bearer token.
    """

    def __init__(self, path: str | Path):
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(AUTH_SESSIONS_DDL)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @classmethod
    def _row_to_session(cls, row: sqlite3.Row) -> dict:
        return {key: row[key] for key in _SESSION_COLUMNS}

    def create_session(
        self,
        *,
        user_id: str,
        token_hash: str,
        expires_at: str,
    ) -> dict:
        """Create a session for the given (already-hashed) token."""
        session = {
            "token_hash": token_hash,
            "user_id": user_id,
            "created_at": _now(),
            "expires_at": expires_at,
        }
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO auth_sessions "
                "(token_hash, user_id, created_at, expires_at) "
                "VALUES (?, ?, ?, ?)",
                (session["token_hash"], session["user_id"],
                 session["created_at"], session["expires_at"]),
            )
        return session

    def get_session(self, token_hash: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM auth_sessions WHERE token_hash = ?",
                (token_hash,),
            ).fetchone()
        return self._row_to_session(row) if row else None

    def delete_session(self, token_hash: str) -> bool:
        """Delete a session by hash; returns whether a row was removed."""
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM auth_sessions WHERE token_hash = ?",
                (token_hash,),
            )
        return cursor.rowcount > 0

    def delete_expired(self, before: str) -> int:
        """Delete sessions expiring before ``before`` (ISO-8601); count removed."""
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM auth_sessions WHERE expires_at <= ?",
                (before,),
            )
        return cursor.rowcount


_session_store: SessionStore | None = None
_session_store_lock = threading.Lock()


def get_session_store() -> SessionStore:
    global _session_store
    with _session_store_lock:
        if _session_store is None:
            _session_store = SessionStore(default_session_store_path())
        return _session_store


def set_session_store(store: SessionStore | None) -> None:
    global _session_store
    with _session_store_lock:
        _session_store = store