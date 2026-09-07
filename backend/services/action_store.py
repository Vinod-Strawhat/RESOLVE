import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from backend.services.case_store import default_case_store_path

ACTION_TYPES = ("warranty_dispute", "refund_request", "return_request", "escalation", "other")

ACTION_FIELDS = ("type", "target", "title", "reason", "content")

VALID_STATUSES = (
    "draft",
    "pending_approval",
    "approved",
    "executing",
    "executed",
    "failed",
    "rejected",
)

_EXECUTION_COLUMNS = (
    ("execution_status", "TEXT"),
    ("executed_at", "TEXT"),
    ("execution_reference", "TEXT"),
    ("execution_result", "TEXT"),
    ("execution_error", "TEXT"),
)

_ACTIONS_DDL = """
CREATE TABLE IF NOT EXISTS actions (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    type TEXT NOT NULL,
    target TEXT,
    title TEXT NOT NULL,
    reason TEXT NOT NULL,
    content TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    execution_status TEXT,
    executed_at TEXT,
    execution_reference TEXT,
    execution_result TEXT,
    execution_error TEXT,
    created_at TEXT NOT NULL,
    approved_at TEXT,
    rejected_at TEXT,
    FOREIGN KEY (case_id) REFERENCES cases (id)
);

CREATE INDEX IF NOT EXISTS idx_actions_case_id ON actions (case_id);
CREATE INDEX IF NOT EXISTS idx_actions_status ON actions (status);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ActionStore:
    """SQLite-backed action records linked to cases."""

    def __init__(self, path: str | Path):
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_ACTIONS_DDL)
        self._ensure_execution_columns()

    def _ensure_execution_columns(self) -> None:
        """Migrate existing actions tables so Phase 6 execution fields exist."""
        with self._connect() as conn:
            existing = {
                row["name"] for row in conn.execute("PRAGMA table_info(actions)")
            }
            for name, declaration in _EXECUTION_COLUMNS:
                if name not in existing:
                    conn.execute(f"ALTER TABLE actions ADD COLUMN {name} {declaration}")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    _COLUMNS = (
        "id",
        "case_id",
        "type",
        "target",
        "title",
        "reason",
        "content",
        "status",
        "execution_status",
        "executed_at",
        "execution_reference",
        "execution_result",
        "execution_error",
        "created_at",
        "approved_at",
        "rejected_at",
    )

    @classmethod
    def _row_to_action(cls, row: sqlite3.Row) -> dict:
        return {key: row[key] for key in cls._COLUMNS}

    def create_action(
        self,
        case_id: str,
        *,
        type: str,
        title: str,
        reason: str,
        content: str,
        target: str = "",
    ) -> dict:
        if type not in ACTION_TYPES:
            raise ValueError(f"invalid action type: {type!r}; allowed: {ACTION_TYPES}")
        if not title or not title.strip():
            raise ValueError("title must not be empty")
        if not reason or not reason.strip():
            raise ValueError("reason must not be empty")
        if not content or not content.strip():
            raise ValueError("content must not be empty")

        action_id = uuid.uuid4().hex
        now = _now()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO actions "
                "(id, case_id, type, target, title, reason, content, status, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 'draft', ?)",
                (
                    action_id,
                    case_id,
                    type.strip(),
                    (target or "").strip(),
                    title.strip(),
                    reason.strip(),
                    content.strip(),
                    now,
                ),
            )
        return self.get_action(action_id)

    def get_action(self, action_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM actions WHERE id = ?", (action_id,)
            ).fetchone()
        return self._row_to_action(row) if row else None

    def list_actions_for_case(self, case_id: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM actions WHERE case_id = ? ORDER BY created_at, rowid",
                (case_id,),
            ).fetchall()
        return [self._row_to_action(row) for row in rows]

    def approve_action(self, action_id: str) -> dict:
        action = self.get_action(action_id)
        if action is None:
            raise ValueError(f"action not found: {action_id}")
        if action["status"] != "pending_approval":
            raise ValueError(
                f"cannot approve action in status {action['status']!r}; "
                "must be pending_approval"
            )
        now = _now()
        with self._connect() as conn:
            conn.execute(
                "UPDATE actions SET status = 'approved', approved_at = ? WHERE id = ?",
                (now, action_id),
            )
        return self.get_action(action_id)

    def reject_action(self, action_id: str) -> dict:
        action = self.get_action(action_id)
        if action is None:
            raise ValueError(f"action not found: {action_id}")
        if action["status"] != "pending_approval":
            raise ValueError(
                f"cannot reject action in status {action['status']!r}; "
                "must be pending_approval"
            )
        now = _now()
        with self._connect() as conn:
            conn.execute(
                "UPDATE actions SET status = 'rejected', rejected_at = ? WHERE id = ?",
                (now, action_id),
            )
        return self.get_action(action_id)

    def submit_for_approval(self, action_id: str) -> dict:
        action = self.get_action(action_id)
        if action is None:
            raise ValueError(f"action not found: {action_id}")
        if action["status"] != "draft":
            raise ValueError(
                f"cannot submit action in status {action['status']!r}; "
                "must be draft"
            )
        now = _now()
        with self._connect() as conn:
            conn.execute(
                "UPDATE actions SET status = 'pending_approval' WHERE id = ?",
                (action_id,),
            )
        return self.get_action(action_id)

    def begin_execution(self, action_id: str) -> dict:
        """Transition an approved action into the executing state.

        Only approved actions may be executed. A completed (executed) action
        must never be executed twice.
        """
        action = self.get_action(action_id)
        if action is None:
            raise ValueError(f"action not found: {action_id}")
        if action["status"] != "approved":
            raise ValueError(
                f"cannot execute action in status {action['status']!r}; "
                "only approved actions may be executed"
            )
        with self._connect() as conn:
            conn.execute(
                "UPDATE actions SET status = 'executing', execution_status = 'executing' "
                "WHERE id = ?",
                (action_id,),
            )
        return self.get_action(action_id)

    def complete_execution(
        self, action_id: str, *, reference: str, result: str
    ) -> dict:
        action = self.get_action(action_id)
        if action is None:
            raise ValueError(f"action not found: {action_id}")
        if action["status"] != "executing":
            raise ValueError(
                f"cannot complete execution in status {action['status']!r}; "
                "must be executing"
            )
        now = _now()
        with self._connect() as conn:
            conn.execute(
                "UPDATE actions SET status = 'executed', execution_status = 'executed', "
                "executed_at = ?, execution_reference = ?, execution_result = ? "
                "WHERE id = ?",
                (now, reference, result, action_id),
            )
        return self.get_action(action_id)

    def fail_execution(self, action_id: str, *, error: str) -> dict:
        action = self.get_action(action_id)
        if action is None:
            raise ValueError(f"action not found: {action_id}")
        if action["status"] != "executing":
            raise ValueError(
                f"cannot fail execution in status {action['status']!r}; "
                "must be executing"
            )
        with self._connect() as conn:
            conn.execute(
                "UPDATE actions SET status = 'failed', execution_status = 'failed', "
                "execution_error = ? WHERE id = ?",
                (error, action_id),
            )
        return self.get_action(action_id)


_action_store: ActionStore | None = None
_action_store_lock = threading.Lock()


def get_action_store() -> ActionStore:
    global _action_store
    with _action_store_lock:
        if _action_store is None:
            _action_store = ActionStore(default_case_store_path())
        return _action_store


def set_action_store(store: ActionStore | None) -> None:
    global _action_store
    with _action_store_lock:
        _action_store = store
