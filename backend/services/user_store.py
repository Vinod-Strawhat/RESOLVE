"""Persistent user accounts (Phase 8A).

Every row stores the Argon2 password hash only - never a plaintext
password.  The store is deliberately unaware of hashing mechanics; the
caller supplies ``password_hash`` via :mod:`backend.services.passwords`.
"""

import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from backend.services.memory_store import default_memory_db_path

USERS_DDL = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    display_name TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

_USER_COLUMNS = (
    "id",
    "email",
    "password_hash",
    "display_name",
    "created_at",
    "updated_at",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_user_store_path() -> Path:
    configured = os.environ.get("MEMORY_DB_PATH")
    if configured:
        return Path(configured)
    return default_memory_db_path()


class DuplicateEmailError(ValueError):
    """Raised when creating a user whose email already exists."""


class UserStore:
    """SQLite-backed user account records."""

    def __init__(self, path: str | Path):
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(USERS_DDL)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @classmethod
    def _row_to_user(cls, row: sqlite3.Row) -> dict:
        return {key: row[key] for key in _USER_COLUMNS}

    def create_user(
        self,
        *,
        email: str,
        password_hash: str,
        display_name: str | None = None,
    ) -> dict:
        if not email or not email.strip():
            raise ValueError("email must not be empty")
        if not password_hash or not password_hash.strip():
            raise ValueError("password_hash must not be empty")
        if self.get_user_by_email(email) is not None:
            raise DuplicateEmailError(
                f"a user with email {email!r} already exists"
            )
        user_id = uuid.uuid4().hex
        now = _now()
        try:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO users "
                    "(id, email, password_hash, display_name, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (user_id, email, password_hash, display_name, now, now),
                )
        except sqlite3.IntegrityError:
            raise DuplicateEmailError(
                f"a user with email {email!r} already exists"
            ) from None
        return self.get_user(user_id)

    def get_user(self, user_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE id = ?", (user_id,)
            ).fetchone()
        return self._row_to_user(row) if row else None

    def get_user_by_email(self, email: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE email = ?", (email,)
            ).fetchone()
        return self._row_to_user(row) if row else None


_user_store: UserStore | None = None
_user_store_lock = threading.Lock()


def get_user_store() -> UserStore:
    global _user_store
    with _user_store_lock:
        if _user_store is None:
            _user_store = UserStore(default_user_store_path())
        return _user_store


def set_user_store(store: UserStore | None) -> None:
    global _user_store
    with _user_store_lock:
        _user_store = store