import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from backend.services.case_store import CASES_DDL, SESSIONS_DDL
from backend.services.memory_store import default_memory_db_path

ALLOWED_EXTENSIONS = {".txt", ".md", ".pdf"}
MAX_UPLOAD_BYTES = 2 * 1024 * 1024

_SCHEMA = SESSIONS_DDL + CASES_DDL + """
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    filename TEXT NOT NULL,
    content_type TEXT,
    size_bytes INTEGER NOT NULL,
    storage_path TEXT NOT NULL,
    extracted_text TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (case_id) REFERENCES cases (id)
);

CREATE INDEX IF NOT EXISTS idx_documents_case_id ON documents (case_id);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_uploads_dir() -> Path:
    configured = os.environ.get("UPLOADS_DIR")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[2] / "database" / "uploads"


class InvalidUploadError(ValueError):
    pass


class DocumentStore:
    """Safe on-disk document storage with SQLite metadata + extracted text."""

    def __init__(self, path: str | Path, uploads_dir: str | Path):
        self._path = Path(path)
        self._uploads = Path(uploads_dir)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._uploads.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def validate(self, filename: str, content_type: str, content: bytes) -> str:
        extension = Path(filename).suffix.lower()
        if extension not in ALLOWED_EXTENSIONS:
            raise InvalidUploadError(
                f"unsupported file type {extension or '(none)'}; allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
            )
        size = len(content)
        if size > MAX_UPLOAD_BYTES:
            raise InvalidUploadError(
                f"file too large: {size} bytes exceeds limit of {MAX_UPLOAD_BYTES} bytes"
            )
        if size == 0:
            raise InvalidUploadError("file is empty")
        if extension == ".pdf" and content_type:
            ok = "pdf" in content_type.lower()
            if not ok:
                raise InvalidUploadError(
                    f"content type {content_type!r} does not match pdf file extension"
                )
        return extension

    def save(self, case_id: str, filename: str, content_type: str, content: bytes) -> dict:
        extension = self.validate(filename, content_type, content)
        doc_id = f"{uuid.uuid4().hex}{extension}"
        storage_path = self._uploads / doc_id
        storage_path.write_bytes(content)
        now = _now()
        record = {
            "id": doc_id,
            "case_id": case_id,
            "filename": filename,
            "content_type": content_type,
            "size_bytes": len(content),
            "storage_path": str(storage_path),
            "extracted_text": None,
            "created_at": now,
        }
        try:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO documents (id, case_id, filename, content_type, size_bytes, "
                    "storage_path, extracted_text, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (record["id"], case_id, filename, content_type, record["size_bytes"],
                     record["storage_path"], record["extracted_text"], now),
                )
        except Exception:
            storage_path.unlink(missing_ok=True)
            raise
        return record

    def set_extracted_text(self, document_id: str, text: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE documents SET extracted_text = ? WHERE id = ?",
                (text, document_id),
            )

    def get_document(self, document_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
        return dict(row) if row else None

    def list_documents(self, case_id: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM documents WHERE case_id = ? ORDER BY created_at, rowid",
                (case_id,),
            ).fetchall()
        return [dict(row) for row in rows]


_document_store: DocumentStore | None = None
_document_store_lock = threading.Lock()


def get_document_store() -> DocumentStore:
    global _document_store
    with _document_store_lock:
        if _document_store is None:
            _document_store = DocumentStore(
                default_memory_db_path(),
                default_uploads_dir(),
            )
        return _document_store


def set_document_store(store: DocumentStore | None) -> None:
    global _document_store
    with _document_store_lock:
        _document_store = store