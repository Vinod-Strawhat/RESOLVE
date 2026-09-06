import uuid

import pytest

from backend.services.case_store import CaseStore
from backend.services.document_store import (
    MAX_UPLOAD_BYTES,
    DocumentStore,
    InvalidUploadError,
)


@pytest.fixture
def store(tmp_path):
    cases = CaseStore(tmp_path / "resolve.db")
    doc_store = DocumentStore(tmp_path / "resolve.db", tmp_path / "uploads")
    doc_store.case_ids = [
        cases.create_case(
            f"session-{index}", title=f"T{index}", category="warranty", description="D"
        )["id"]
        for index in range(1, 6)
    ]
    return doc_store


def _missing_case():
    return uuid.uuid4().hex


def test_save_document_records_metadata(store):
    doc = store.save(
        case_id=store.case_ids[0],
        filename="invoice.txt",
        content_type="text/plain",
        content=b"Invoice content",
    )
    assert doc["id"].endswith(".txt")
    assert doc["case_id"] == store.case_ids[0]
    assert doc["filename"] == "invoice.txt"
    assert doc["size_bytes"] == 15
    assert doc["extracted_text"] is None
    assert doc["created_at"]


def test_save_document_stores_file_in_uploads_dir(store):
    doc = store.save(
        case_id=store.case_ids[0],
        filename="warranty.pdf",
        content_type="application/pdf",
        content=b"%PDF-1.4",
    )
    assert doc["storage_path"] == str(store._uploads / doc["id"])
    stored = store._uploads / doc["id"]
    assert stored.exists()
    assert stored.read_bytes() == b"%PDF-1.4"


def test_generated_filename_ignores_client_path(store):
    doc = store.save(
        case_id=store.case_ids[0],
        filename="../../secret/invoice.txt",
        content_type="text/plain",
        content=b"data",
    )
    assert ".." not in doc["id"]
    assert str(store._uploads / doc["id"]) == doc["storage_path"]


def test_rejects_unsupported_extension(store):
    with pytest.raises(InvalidUploadError, match="unsupported file type"):
        store.save(case_id=store.case_ids[0], filename="virus.exe", content_type="application/octet-stream", content=b"x")


def test_rejects_empty_file(store):
    with pytest.raises(InvalidUploadError, match="empty"):
        store.save(case_id=store.case_ids[0], filename="doc.txt", content_type="text/plain", content=b"")


def test_rejects_oversized_file(store):
    with pytest.raises(InvalidUploadError, match="too large"):
        store.save(
            case_id=store.case_ids[0],
            filename="big.txt",
            content_type="text/plain",
            content=b"x" * (MAX_UPLOAD_BYTES + 1),
        )


def test_rejects_filename_mime_mismatch_for_pdf(store):
    with pytest.raises(InvalidUploadError, match="content type"):
        store.save(case_id=store.case_ids[0], filename="doc.pdf", content_type="text/plain", content=b"%PDF-1.4")


def test_missing_case_rejected_by_foreign_key(store):
    with pytest.raises(Exception):
        store.save(case_id=_missing_case(), filename="doc.txt", content_type="text/plain", content=b"x")


def test_set_and_get_extracted_text(store):
    doc = store.save(case_id=store.case_ids[0], filename="doc.txt", content_type="text/plain", content=b"x")
    store.set_extracted_text(doc["id"], "extracted words")
    assert store.get_document(doc["id"])["extracted_text"] == "extracted words"


def test_list_documents_scoped_to_case(store):
    store.save(case_id=store.case_ids[0], filename="a.txt", content_type="text/plain", content=b"a")
    store.save(case_id=store.case_ids[0], filename="b.pdf", content_type="application/pdf", content=b"%PDF")
    store.save(case_id=store.case_ids[1], filename="c.txt", content_type="text/plain", content=b"c")
    docs = store.list_documents(store.case_ids[0])
    assert [d["filename"] for d in docs] == ["a.txt", "b.pdf"]
    assert len(store.list_documents(store.case_ids[1])) == 1


def test_uploads_dir_created(store, tmp_path):
    uploads = tmp_path / "uploads"
    assert uploads.is_dir()