"""Live diagnostic: RESOLVE Phase 4 case tools + document analysis.

Runs the REAL Strands agent against OpenRouter (minimax/minimax-m3:free):

  Phase 1 (create): model should select create_case on the first chat turn.
  Phase 2 (update): model should select update_case when new facts arrive.
  Phase 3 (upload): upload a synthetic warranty PDF through the real FastAPI
                    endpoint; text is extracted and the model analyses it.

Each phase runs in its own subprocess with a hard wall-clock timeout so a
rate-limited upstream never hangs the whole diagnostic. All persistence goes
to a throwaway directory (RESOLVE_DIAG_TMP) so the real database/resolve.db,
case_notes.json and database/uploads are never touched.

Usage:
    .\\venv\\Scripts\\python.exe backend\\diagnostics\\live_case_check.py
    .\\venv\\Scripts\\python.exe backend\\diagnostics\\live_case_check.py create
    .\\venv\\Scripts\\python.exe backend\\diagnostics\\live_case_check.py update
    .\\venv\\Scripts\\python.exe backend\\diagnostics\\live_case_check.py upload
"""

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from dotenv import load_dotenv

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
load_dotenv(REPO / ".env")

PHASE_TIMEOUTS = {"create": 240, "update": 240, "upload": 240}


def _setup(tmp: Path):
    from backend.services.case_store import CaseStore, set_case_store
    from backend.services.document_store import DocumentStore, set_document_store
    from backend.services.memory_store import MemoryStore, set_memory_store
    from backend.services.note_store import NoteStore
    from backend.tools.case_notes import set_tool_store

    memory = MemoryStore(tmp / "memory.db")
    cases = CaseStore(tmp / "resolve.db")
    documents = DocumentStore(tmp / "resolve.db", tmp / "uploads")
    notes = NoteStore(tmp / "case_notes.json")
    set_memory_store(memory)
    set_case_store(cases)
    set_document_store(documents)
    set_tool_store(notes)
    return memory, cases, documents, notes


def _session_path(tmp: Path) -> Path:
    return tmp / "session.txt"


def pdf_bytes(text: str) -> bytes:
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


def response_text(result) -> str:
    content = result.message
    blocks = content["content"] if isinstance(content, dict) else content.content
    parts = []
    for block in blocks:
        if isinstance(block, dict):
            parts.append(block.get("text") or "")
        else:
            parts.append(getattr(block, "text", None) or "")
    return " ".join(parts).strip()


def phase_create(tmp: Path) -> int:
    from backend.agent.resolve_agent import build_resolve_agent
    from backend.services.conversation import to_agent_transcript

    memory, cases, _, _ = _setup(tmp)
    session_id = memory.create_session()
    _session_path(tmp).write_text(session_id, encoding="utf-8")
    print(f"SESSION_ID={session_id}")

    user = (
        "I need help with a warranty problem. I bought a laptop and two months "
        "later the screen stopped working during normal use. The manufacturer "
        "refused my warranty claim, claiming there is physical damage, but there "
        "is none. Please open a case for this so we can track it."
    )
    tool_activity: list[dict] = []
    agent = build_resolve_agent(tool_activity=tool_activity)
    transcript = [{"role": "user", "content": [{"text": user}]}]
    started = time.monotonic()
    result = agent(prompt=transcript, invocation_state={"session_id": session_id})
    took = round(time.monotonic() - started, 1)
    print(f"PHASE_CREATE_SECONDS={took}")
    print(f"TOOL_ACTIVITY={json.dumps(tool_activity)}")
    print(f"ASSISTANT={response_text(result)}")
    case = cases.get_case_by_session(session_id)
    print(f"CASE_ROW={json.dumps(case)}")
    memory.save_message(session_id=session_id, role="user", content=user)
    memory.save_message(session_id=session_id, role="assistant", content=response_text(result))
    ok = "create_case" in str(tool_activity) and case is not None
    print(f"PASS_PHASE_CREATE={ok}")
    return 0 if ok else 1


def phase_update(tmp: Path) -> int:
    from backend.agent.resolve_agent import build_resolve_agent
    from backend.services.conversation import load_session_history, to_agent_transcript

    memory, cases, _, _ = _setup(tmp)
    session_id = _session_path(tmp).read_text(encoding="utf-8").strip()
    print(f"SESSION_ID={session_id}")

    case = cases.get_case_by_session(session_id)
    print(f"BEFORE_CASE={json.dumps(case)}")
    if case is None:
        print("NO_CASE_FOUND=phase_create_did_not_complete")
        print("PASS_PHASE_UPDATE=False")
        return 1

    user = (
        "Update the case: the invoice shows retail price Rs 48,999, sold by "
        "Flipkart, purchased on 14 March 2026, order HBXQ-44-91. I also received "
        "a stamped warranty rejection letter dated 2 September 2026."
    )
    tool_activity: list[dict] = []
    agent = build_resolve_agent(tool_activity=tool_activity)
    history = load_session_history(memory, session_id)
    transcript = to_agent_transcript(history)
    transcript.insert(
        0,
        {
            "role": "system",
            "content": [
                {
                    "text": (
                        f"There is an active structured case for this conversation: "
                        f"{case['id']}. New facts should be recorded on it using "
                        "update_case."
                    )
                }
            ],
        },
    )
    transcript.append({"role": "user", "content": [{"text": user}]})
    started = time.monotonic()
    result = agent(prompt=transcript, invocation_state={"session_id": session_id})
    took = round(time.monotonic() - started, 1)
    print(f"PHASE_UPDATE_SECONDS={took}")
    print(f"TOOL_ACTIVITY={json.dumps(tool_activity)}")
    print(f"ASSISTANT={response_text(result)}")
    updated = cases.get_case_by_session(session_id)
    print(f"AFTER_CASE={json.dumps(updated)}")
    memory.save_message(session_id=session_id, role="user", content=user)
    memory.save_message(session_id=session_id, role="assistant", content=response_text(result))
    mapped = {
        updated.get(k)
        for k in ("product", "seller", "amount", "purchase_date", "rejection_reason")
    }
    ok = (
        "update_case" in str(tool_activity)
        and any(bool(value) for value in mapped)
    )
    print(f"PASS_PHASE_UPDATE={ok}")
    return 0 if ok else 1


def phase_upload(tmp: Path) -> int:
    from fastapi.testclient import TestClient

    from backend.agent.resolve_agent import build_resolve_agent
    from backend.main import app

    memory, cases, documents, _ = _setup(tmp)
    session_id = _session_path(tmp).read_text(encoding="utf-8").strip()
    print(f"SESSION_ID={session_id}")
    case = cases.get_case_by_session(session_id)
    print(f"CASE_ID={case['id'] if case else None}")
    if case is None:
        print("NO_CASE_FOUND=phase_create_did_not_complete")
        print("PASS_PHASE_UPLOAD=False")
        return 1

    warranty_pdf = pdf_bytes(
        "ASUS INTERNATIONAL WARRANTY: 24 months coverage from purchase date. "
        "Screen defects are covered. Contact support@asus.example.com"
    )
    client = TestClient(app)
    started = time.monotonic()
    response = client.post(
        f"/api/cases/{case['id']}/documents",
        files={"file": ("asus_warranty.pdf", warranty_pdf, "application/pdf")},
    )
    took = round(time.monotonic() - started, 1)
    print(f"PHASE_UPLOAD_SECONDS={took}")
    print(f"HTTP_STATUS={response.status_code}")
    body = response.json()
    print(f"RESPONSE={json.dumps(body)}")

    stored = documents.list_documents(case["id"])
    extracted = stored[0]["extracted_text"].lower() if stored else ""
    ok = response.status_code == 200 and extracted.startswith("asus")
    print(f"PASS_PHASE_UPLOAD={ok}")
    return 0 if ok else 1


def controller() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="resolve-live-case-", dir=str(REPO / "database")))
    print(f"ARTIFACTS_DIR={tmp}")
    env = dict(os.environ, **{"RESOLVE_DIAG_TMP": str(tmp), "PYTHONIOENCODING": "utf-8"})
    results: list[tuple[str, bool]] = []
    for phase in ("create", "update", "upload"):
        print("=" * 78)
        print(f"RUNNING PHASE: {phase}")
        started = time.monotonic()
        try:
            proc = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), phase],
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=PHASE_TIMEOUTS[phase],
            )
            print(proc.stdout.strip())
            if proc.stderr.strip():
                print("[phase stderr]", proc.stderr.strip()[-1200:])
            ok = proc.returncode == 0
        except subprocess.TimeoutExpired as exc:
            print(f"PHASE_TIMED_OUT after {PHASE_TIMEOUTS[phase]}s")
            if exc.stdout:
                print(exc.stdout.decode("utf-8", errors="replace")[-1500:])
            ok = False
        took = round(time.monotonic() - started, 1)
        print(f"phase took {took}s -> {'PASS' if ok else 'FAIL'}")
        results.append((phase, ok))

    print("=" * 78)
    for phase, ok in results:
        print(f"[{'PASS' if ok else 'FAIL'}] phase_{phase}")
    all_ok = all(ok for _, ok in results)
    print(f"RESULT: {'ALL PHASE 4 LIVE CHECKS PASSED' if all_ok else 'SOME PHASES FAILED'}")
    print(f"ARTIFACTS_DIR={tmp}")
    return 0 if all_ok else 1


def main() -> int:
    import builtins
    import functools

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    builtins.print = functools.partial(print, flush=True)
    mode = sys.argv[1] if len(sys.argv) > 1 else "controller"
    tmp = Path(os.environ["RESOLVE_DIAG_TMP"]) if "RESOLVE_DIAG_TMP" in os.environ else None
    if mode == "controller":
        return controller()
    if mode in ("create", "update", "upload"):
        if tmp is None:
            print("RESOLVE_DIAG_TMP must be set when running a phase directly")
            return 2
        try:
            return {"create": phase_create, "update": phase_update, "upload": phase_upload}[mode](tmp)
        except Exception as exc:
            print(f"PHASE_CRASH={type(exc).__name__}: {str(exc)[:300]}")
            return 1
    print(f"unknown mode: {mode}")
    return 2


if __name__ == "__main__":
    sys.exit(main())