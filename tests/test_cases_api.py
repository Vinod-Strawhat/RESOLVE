import io
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter

from backend.main import app
from backend.services.case_store import CaseStore
from backend.services.document_store import DocumentStore
from backend.services.memory_store import MemoryStore


class FakeAgent:
    def __init__(self):
        self.prompts = []

    def __call__(self, prompt, **kwargs):
        self.prompts.append(prompt)
        message = SimpleNamespace(content=[{"text": "I reviewed the document."}])
        return SimpleNamespace(message=message, stop_reason="end_turn")


@pytest.fixture
def env(tmp_path, monkeypatch):
    db = tmp_path / "resolve.db"
    cases = CaseStore(db)
    documents = DocumentStore(db, tmp_path / "uploads")
    memory = MemoryStore(db)
    monkeypatch.setattr("backend.api.cases.get_case_store", lambda: cases)
    monkeypatch.setattr("backend.api.cases.get_document_store", lambda: documents)
    monkeypatch.setattr("backend.api.cases.get_memory_store", lambda: memory)
    case_id = cases.create_case(
        "session-1",
        title="Rejected warranty claim",
        category="warranty",
        description="Company refused to fix the laptop.",
    )["id"]
    return {"case_id": case_id, "cases": cases, "memory": memory}


@pytest.fixture
def fake_agent():
    return FakeAgent()


@pytest.fixture
def client(env, monkeypatch, fake_agent):
    monkeypatch.setattr("backend.api.cases.build_resolve_agent", lambda tool_activity=None: fake_agent)
    return TestClient(app)


def _upload(client, case_id, filename, content=b"laptop", content_type="text/plain"):
    return client.post(
        f"/api/cases/{case_id}/documents",
        files={"file": (filename, content, content_type)},
    )


def test_get_case_returns_case_and_documents(client, env):
    response = client.get(f"/api/cases/{env['case_id']}")
    assert response.status_code == 200
    body = response.json()
    assert body["case"]["category"] == "warranty"
    assert body["documents"] == []


def test_get_case_missing_returns_404(client):
    assert client.get("/api/cases/missing").status_code == 404


def test_upload_document_to_missing_case_returns_404(client):
    assert _upload(client, "missing-case", "doc.txt").status_code == 404


def test_upload_txt_document(client, env):
    response = _upload(client, env["case_id"], "invoice.txt", b"ASUS Vivobook notebook")
    assert response.status_code == 200
    body = response.json()
    assert body["document"]["filename"] == "invoice.txt"
    assert body["case"]["id"] == env["case_id"]
    assert body["document"]["extracted_text"] == "ASUS Vivobook notebook"
    assert "storage_path" not in body["document"]
    assert body["analysis"]["response"] == "I reviewed the document."


def test_upload_document_text_reaches_agent(client, env, fake_agent):
    _upload(client, env["case_id"], "invoice.txt", b"ASUS Vivobook, purchased March 2026")
    assert len(fake_agent.prompts) == 1
    last_message = fake_agent.prompts[0][-1]["content"][0]["text"]
    assert "ASUS Vivobook" in last_message
    assert "purchased March 2026" in last_message
    assert "invoice.txt" in last_message


def test_upload_agent_analysis_saved_to_memory(client, env):
    _upload(client, env["case_id"], "invoice.txt", b"laptop")
    messages = env["memory"].list_messages("session-1")
    roles = [m["role"] for m in messages]
    assert roles == ["user", "assistant"]
    assert messages[-1]["content"] == "I reviewed the document."


def test_upload_rejects_unsupported_extension(client, env):
    response = _upload(client, env["case_id"], "photo.png", b"image", "image/png")
    assert response.status_code == 400
    assert "unsupported file type" in response.json()["detail"]


def test_upload_rejects_empty_file(client, env):
    response = _upload(client, env["case_id"], "empty.txt", b"")
    assert response.status_code == 400
    assert "empty" in response.json()["detail"]


def test_upload_rejects_oversized_file(client, env):
    response = _upload(client, env["case_id"], "big.txt", b"x" * (2 * 1024 * 1024 + 1))
    assert response.status_code == 400
    assert "too large" in response.json()["detail"]


def test_upload_pdf_document(client, env):
    pdf = _pdf_bytes("Invoice shows ASUS Vivobook Rs 35000")
    response = _upload(client, env["case_id"], "invoice.pdf", pdf, "application/pdf")
    assert response.status_code == 200
    assert "ASUS Vivobook" in response.json()["document"]["extracted_text"]


def test_upload_scanned_pdf_no_readable_text(client, env):
    response = _upload(client, env["case_id"], "scan.pdf", _blank_pdf(), "application/pdf")
    assert response.status_code == 200
    assert response.json()["document"]["extracted_text"] == ""


def test_upload_failure_saves_no_messages(client, env):
    response = _upload(client, env["case_id"], "trololo.pdf", b"%PDF", "text/plain")
    assert response.status_code == 400
    assert env["memory"].list_messages("session-1") == []


def _pdf_bytes(text: str) -> bytes:
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>"
        ),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    body = bytearray(b"%PDF-1.4\n")
    offsets = []
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(body))
        body += f"{index} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref_pos = len(body)
    body += b"xref\n0 6\n0000000000 65535 f \n"
    for offset in offsets:
        body += f"{offset:010d} 00000 n \n".encode()
    body += b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n" + str(xref_pos).encode() + b"\n%%EOF"
    return bytes(body)


def _blank_pdf() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()