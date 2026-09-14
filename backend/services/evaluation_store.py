"""Persistent store for response evaluations (Phase 7B-1).

Each row records one response evaluation - whether it came from the
deterministic manual path (``source="manual"``) or the AI evaluator
(``source="ai"``).  The store is purely durable storage; it never decides
state transitions and never reads or writes case/action state.

Outcomes are the existing resolution outcomes exposed by
:data:`backend.services.case_store.EVALUATION_OUTCOMES`; no new outcome
values are introduced here.
"""

import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from backend.services.case_store import EVALUATION_OUTCOMES
from backend.services.memory_store import default_memory_db_path

EVALUATION_SOURCES = ("manual", "ai")

EVALUATIONS_DDL = """
CREATE TABLE IF NOT EXISTS evaluations (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    outcome TEXT NOT NULL,
    confidence REAL,
    reason TEXT,
    next_step TEXT,
    source TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (case_id) REFERENCES cases (id)
);

CREATE INDEX IF NOT EXISTS idx_evaluations_case_id ON evaluations (case_id);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_path() -> Path:
    configured = os.environ.get("MEMORY_DB_PATH")
    if configured:
        return Path(configured)
    return default_memory_db_path()


class EvaluationStore:
    """SQLite-backed record of manual/AI response evaluations per case."""

    def __init__(self, path: str | Path):
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(EVALUATIONS_DDL)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    _COLUMNS = (
        "id",
        "case_id",
        "outcome",
        "confidence",
        "reason",
        "next_step",
        "source",
        "created_at",
    )

    @classmethod
    def _row_to_evaluation(cls, row: sqlite3.Row) -> dict:
        return {key: row[key] for key in cls._COLUMNS}

    def record_evaluation(
        self,
        case_id: str,
        *,
        outcome: str,
        source: str,
        confidence: float = 0.0,
        reason: str = "",
        next_step: str = "",
    ) -> dict:
        outcome = outcome.strip()
        source = source.strip()
        if outcome not in EVALUATION_OUTCOMES:
            raise ValueError(
                f"invalid evaluation outcome {outcome!r}; "
                f"allowed: {', '.join(sorted(EVALUATION_OUTCOMES))}"
            )
        if source not in EVALUATION_SOURCES:
            raise ValueError(
                f"invalid evaluation source {source!r}; "
                f"allowed: {', '.join(EVALUATION_SOURCES)}"
            )
        try:
            confidence = float(confidence)
        except (TypeError, ValueError):
            raise ValueError(f"confidence must be numeric, got {confidence!r}") from None

        now = _now()
        evaluation = {
            "id": uuid.uuid4().hex,
            "case_id": case_id,
            "outcome": outcome,
            "confidence": confidence,
            "reason": reason.strip(),
            "next_step": next_step.strip(),
            "source": source,
            "created_at": now,
        }
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO evaluations "
                "(id, case_id, outcome, confidence, reason, next_step, source, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    evaluation["id"],
                    case_id,
                    outcome,
                    confidence,
                    evaluation["reason"],
                    evaluation["next_step"],
                    source,
                    now,
                ),
            )
        return evaluation

    def get_evaluation(self, evaluation_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM evaluations WHERE id = ?", (evaluation_id,)
            ).fetchone()
        return self._row_to_evaluation(row) if row else None

    def list_evaluations_for_case(self, case_id: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM evaluations WHERE case_id = ? "
                "ORDER BY created_at, rowid",
                (case_id,),
            ).fetchall()
        return [self._row_to_evaluation(row) for row in rows]


_evaluation_store: EvaluationStore | None = None
_evaluation_store_lock = threading.Lock()


def get_evaluation_store() -> EvaluationStore:
    global _evaluation_store
    with _evaluation_store_lock:
        if _evaluation_store is None:
            _evaluation_store = EvaluationStore(_default_path())
        return _evaluation_store


def set_evaluation_store(store: EvaluationStore | None) -> None:
    global _evaluation_store
    with _evaluation_store_lock:
        _evaluation_store = store