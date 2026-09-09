"""Follow-up attempt tracking (Phase 6C).

Records each AI evaluation that returns ``needs_follow_up`` so the backend can
enforce a configurable maximum number of follow-up attempts per case.  The LLM
never reads or writes this table; enforcement is purely server-side.
"""

import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from backend.services.memory_store import default_memory_db_path

DEFAULT_MAX_FOLLOWUPS = 3

FOLLOWUP_DDL = """
CREATE TABLE IF NOT EXISTS followup_attempts (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    attempt_number INTEGER NOT NULL,
    evaluation_reason TEXT,
    evaluation_confidence REAL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (case_id) REFERENCES cases (id)
);

CREATE INDEX IF NOT EXISTS idx_followup_case_id ON followup_attempts (case_id);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_path() -> Path:
    configured = os.environ.get("MEMORY_DB_PATH")
    if configured:
        return Path(configured)
    return default_memory_db_path()


def get_max_followups() -> int:
    raw = os.environ.get("MAX_FOLLOWUPS")
    if raw is not None:
        try:
            value = int(raw)
            if value >= 0:
                return value
        except (ValueError, TypeError):
            pass
    return DEFAULT_MAX_FOLLOWUPS


class FollowupStore:
    """SQLite-backed tracking of AI ``needs_follow_up`` evaluations per case."""

    def __init__(self, path: str | Path):
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(FOLLOWUP_DDL)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    _COLUMNS = (
        "id",
        "case_id",
        "attempt_number",
        "evaluation_reason",
        "evaluation_confidence",
        "created_at",
    )

    @classmethod
    def _row_to_record(cls, row: sqlite3.Row) -> dict:
        return {key: row[key] for key in cls._COLUMNS}

    def get_followup_count(self, case_id: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM followup_attempts WHERE case_id = ?",
                (case_id,),
            ).fetchone()
        return row["cnt"] if row else 0

    def record_followup(
        self,
        case_id: str,
        *,
        reason: str = "",
        confidence: float = 0.0,
    ) -> dict:
        count = self.get_followup_count(case_id)
        attempt_number = count + 1
        record_id = uuid.uuid4().hex
        now = _now()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO followup_attempts "
                "(id, case_id, attempt_number, evaluation_reason, "
                "evaluation_confidence, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (record_id, case_id, attempt_number, reason, confidence, now),
            )
        return {
            "id": record_id,
            "case_id": case_id,
            "attempt_number": attempt_number,
            "evaluation_reason": reason,
            "evaluation_confidence": confidence,
            "created_at": now,
        }

    def get_followup_history(self, case_id: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM followup_attempts WHERE case_id = ? "
                "ORDER BY attempt_number, created_at, rowid",
                (case_id,),
            ).fetchall()
        return [self._row_to_record(row) for row in rows]


_followup_store: FollowupStore | None = None
_followup_store_lock = threading.Lock()


def get_followup_store() -> FollowupStore:
    global _followup_store
    with _followup_store_lock:
        if _followup_store is None:
            _followup_store = FollowupStore(_default_path())
        return _followup_store


def set_followup_store(store: FollowupStore | None) -> None:
    global _followup_store
    with _followup_store_lock:
        _followup_store = store
