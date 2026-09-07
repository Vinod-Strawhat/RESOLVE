"""Live verification of Phase 5 API approval flow against a real agent-created action.

Usage:
    .\\venv\\Scripts\\python.exe backend\\diagnostics\\live_approval_check.py <artifacts_dir> <session_id>
"""

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
load_dotenv(REPO / ".env")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if len(sys.argv) != 3:
        print("usage: live_approval_check.py <artifacts_dir> <session_id>")
        return 2
    artifacts = Path(sys.argv[1])
    session_id = sys.argv[2]

    from fastapi.testclient import TestClient

    from backend.main import app
    from backend.services.action_store import ActionStore, set_action_store
    from backend.services.case_store import CaseStore, set_case_store
    from backend.services.document_store import DocumentStore, set_document_store
    from backend.services.memory_store import MemoryStore, set_memory_store
    from backend.services.note_store import NoteStore
    from backend.tools.case_notes import set_tool_store

    memory = MemoryStore(artifacts / "memory.db")
    cases = CaseStore(artifacts / "resolve.db")
    documents = DocumentStore(artifacts / "resolve.db", artifacts / "uploads")
    actions = ActionStore(artifacts / "resolve.db")
    notes = NoteStore(artifacts / "case_notes.json")
    set_memory_store(memory)
    set_case_store(cases)
    set_document_store(documents)
    set_action_store(actions)
    set_tool_store(notes)

    case = cases.get_case_by_session(session_id)
    print(f"SESSION_ID={session_id}")
    print(f"CASE_ID={case['id']}")
    action = actions.list_actions_for_case(case["id"])[-1]
    print(f"ACTION_ID={action['id']}")
    print(f"ACTION_STATUS={action['status']}")

    client = TestClient(app)

    listed = client.get(f"/api/cases/{case['id']}/actions")
    print(f"LIST_HTTP_STATUS={listed.status_code}")
    print(f"LIST_BODY={json.dumps(listed.json())}")

    fetched = client.get(f"/api/actions/{action['id']}")
    print(f"GET_HTTP_STATUS={fetched.status_code}")
    print(f"GET_BODY={json.dumps(fetched.json())}")

    approved = client.post(f"/api/actions/{action['id']}/approve")
    print(f"APPROVE_HTTP_STATUS={approved.status_code}")
    print(f"APPROVE_BODY={json.dumps(approved.json())}")

    again = client.post(f"/api/actions/{action['id']}/approve")
    print(f"REAPPROVE_HTTP_STATUS={again.status_code}")
    print(f"REAPPROVE_DETAIL={again.json().get('detail')}")

    final = actions.get_action(action["id"])
    print(f"FINAL_STATUS={final['status']}")
    print(f"FINAL_APPROVED_AT={final['approved_at']}")
    print(f"NO_STORAGE_PATH_IN_API={all('storage_path' not in payload for payload in [fetched.json(), approved.json(), listed.json()])}")
    ok = (
        listed.status_code == 200
        and fetched.status_code == 200
        and approved.status_code == 200
        and approved.json()["action"]["status"] == "approved"
        and again.status_code == 409
    )
    print(f"LIVE_APPROVAL_OK={ok}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())