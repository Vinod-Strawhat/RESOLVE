import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from backend.services.memory_store import default_memory_db_path

CASE_FIELDS = (
    "category",
    "title",
    "description",
    "product",
    "amount",
    "purchase_date",
    "seller",
    "warranty_expiry",
    "rejection_reason",
    "status",
    "next_action",
)

SESSIONS_DDL = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

CASES_DDL = """
CREATE TABLE IF NOT EXISTS cases (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    category TEXT,
    title TEXT,
    description TEXT,
    product TEXT,
    amount REAL,
    purchase_date TEXT,
    seller TEXT,
    warranty_expiry TEXT,
    rejection_reason TEXT,
    status TEXT,
    next_action TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions (id)
);

CREATE INDEX IF NOT EXISTS idx_cases_session_id ON cases (session_id);
"""

_SCHEMA = SESSIONS_DDL + CASES_DDL


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_case_store_path() -> Path:
    configured = os.environ.get("MEMORY_DB_PATH")
    if configured:
        return Path(configured)
    return default_memory_db_path()


class CaseStore:
    """SQLite-backed structured case record linked to a conversation session."""

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

    _COLUMNS = (
        "id",
        "session_id",
        "category",
        "title",
        "description",
        "product",
        "amount",
        "purchase_date",
        "seller",
        "warranty_expiry",
        "rejection_reason",
        "status",
        "next_action",
        "created_at",
        "updated_at",
    )

    _FIELDS_TO_COLUMNS = {
        field: field for field in CASE_FIELDS
    }

    @classmethod
    def _row_to_case(cls, row: sqlite3.Row) -> dict:
        return {key: row[key] for key in cls._COLUMNS}

    @classmethod
    def valid_field(cls, field: str) -> bool:
        return field in CASE_FIELDS

    @classmethod
    def normalize_value(cls, field: str, value: str) -> str | float:
        text = str(value).strip()
        if field == "amount":
            if not text:
                raise ValueError("amount must not be empty")
            try:
                return float(text)
            except ValueError as exc:
                raise ValueError(f"amount must be numeric, got {text!r}") from exc
        return text

    def create_case(
        self,
        session_id: str,
        *,
        title: str,
        category: str,
        description: str,
        **optional_fields: str,
    ) -> dict:
        if self.get_case_by_session(session_id) is not None:
            raise ValueError("a case already exists for this session; use update_case")
        case_id = uuid.uuid4().hex
        now = _now()
        values = {
            "id": case_id,
            "session_id": session_id,
            "title": title,
            "category": category,
            "description": description,
            "created_at": now,
            "updated_at": now,
        }
        for field, value in optional_fields.items():
            if field in CASE_FIELDS:
                values[field] = self.normalize_value(field, value)
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO sessions (id, created_at, updated_at) VALUES (?, ?, ?)",
                (session_id, now, now),
            )
            placeholders = ", ".join(values)
            marks = ", ".join("?" for _ in values)
            conn.execute(
                f"INSERT INTO cases ({placeholders}) VALUES ({marks})",
                tuple(values.values()),
            )
        return self.get_case(case_id)

    def get_case(self, case_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM cases WHERE id = ?", (case_id,)).fetchone()
        return self._row_to_case(row) if row else None

    def get_case_by_session(self, session_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM cases WHERE session_id = ? ORDER BY created_at, rowid LIMIT 1",
                (session_id,),
            ).fetchone()
        return self._row_to_case(row) if row else None

    def update_case(self, case_id: str, updates: dict[str, str]) -> dict:
        case = self.get_case(case_id)
        if case is None:
            raise ValueError(f"case not found: {case_id}")

        invalid = [field for field in updates if not self.valid_field(field)]
        if invalid:
            raise ValueError(f"invalid case fields: {', '.join(sorted(invalid))}")

        for field, value in updates.items():
            if not value or not str(value).strip():
                raise ValueError(f"value for {field!r} must not be empty")

        normalized = {
            field: self.normalize_value(field, value) for field, value in updates.items()
        }
        now = _now()
        columns = ", ".join(f"{field} = ?" for field in normalized)
        params = tuple(normalized.values()) + (now, case_id)
        with self._connect() as conn:
            conn.execute(
                f"UPDATE cases SET {columns}, updated_at = ? WHERE id = ?",
                params,
            )
        return self.get_case(case_id)

    def list_cases(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM cases ORDER BY created_at, rowid").fetchall()
        return [self._row_to_case(row) for row in rows]


_case_store: CaseStore | None = None
_case_store_lock = threading.Lock()


def get_case_store() -> CaseStore:
    global _case_store
    with _case_store_lock:
        if _case_store is None:
            _case_store = CaseStore(default_case_store_path())
        return _case_store


def set_case_store(store: CaseStore | None) -> None:
    global _case_store
    with _case_store_lock:
        _case_store = store