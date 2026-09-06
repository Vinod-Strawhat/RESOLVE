import json
import os
import threading
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from backend.agent.resolve_agent import build_resolve_agent
from backend.services.conversation import load_session_history, to_agent_transcript
from backend.services.memory_store import MemoryStore, default_memory_db_path

print(f"OPENROUTER_API_KEY present: {'YES' if os.environ.get('OPENROUTER_API_KEY') else 'NO'}")
print(f"OPENROUTER_MODEL={os.environ.get('OPENROUTER_MODEL')}")

DB = default_memory_db_path()
print(f"MEMORY DB: {DB}")

NOTES = Path(__file__).resolve().parents[2] / "database" / "case_notes.json"


def notes_before():
    if not NOTES.exists():
        return ""
    return NOTES.read_text(encoding="utf-8")


def new_notes(before: str) -> list[dict]:
    if not NOTES.exists():
        return []
    records = json.loads(NOTES.read_text(encoding="utf-8"))
    return [r for r in records if json.dumps(r) not in (json.dumps(b) for b in json.loads(before or "[]"))]


def extract_text(result) -> str:
    content = result.message
    if content is None:
        return ""
    blocks = content["content"] if isinstance(content, dict) else content.content
    parts = []
    for block in blocks:
        if isinstance(block, dict):
            text = block.get("text")
        else:
            text = getattr(block, "text", None)
        if text:
            parts.append(text)
    return " ".join(parts).strip()


def invoke(store: MemoryStore, session_id: str, message: str) -> dict:
    out: dict = {"tool_activity": [], "notes_before": ""}

    def _run() -> None:
        try:
            out["notes_before"] = notes_before()
            agent = build_resolve_agent(tool_activity=out["tool_activity"])
            store.save_message(session_id, "user", message)
            history = load_session_history(store, session_id)
            transcript = to_agent_transcript(history)
            out["transcript_roles"] = [m["role"] for m in transcript]
            out["started"] = time.time()
            result = agent(prompt=transcript)
            out["elapsed"] = time.time() - out["started"]
            out["stop_reason"] = result.stop_reason
            out["response"] = extract_text(result)
            store.save_message(session_id, "assistant", out["response"])
        except Exception as exc:
            out["error"] = repr(exc)[:600]

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    thread.join(90)
    if thread.is_alive():
        out["hang"] = True
    return out


def report(label: str, store: MemoryStore, session_id: str, out: dict) -> None:
    print(f"\n=== {label} ===\n  session_id: {session_id}")
    if out.get("hang"):
        print("  RESULT: HANG (no completion within 90s)")
    elif "error" in out:
        print(f"  RESULT: ERROR {out['error']}")
    else:
        print(f"  RESULT: COMPLETED in {out.get('elapsed', 0):.1f}s  stop_reason: {out.get('stop_reason')}")
        print(f"  response: {out.get('response', '')!r}")
        created = new_notes(out.get("notes_before", ""))
        print(f"  tool_activity: {out['tool_activity']}")
        print(f"  create_case_note notes created this turn: {[r['category'] for r in created]}")
    messages = store.list_messages(session_id)
    print(f"  stored messages: {[(m['role'], m['content']) for m in messages]}")
    print(f"  transcript passed to agent (roles): {out.get('transcript_roles')}")


store = MemoryStore(DB)

warranty_session = store.create_session()
print(f"\nNEW SESSION CALLED: {warranty_session}")
report("TURN 1 (warranty)", store, warranty_session, invoke(store, warranty_session, "My laptop warranty claim was rejected because the company says the damage is not covered."))
time.sleep(8)
report("TURN 2 (same session, follow-up)", store, warranty_session, invoke(store, warranty_session, "It's an ASUS Vivobook. I bought it in March 2026."))
time.sleep(8)

greeting_session = store.create_session()
report("GREETING (negative test)", store, greeting_session, invoke(store, greeting_session, "Hello, how are you?"))

print("\n=== RESTART PERSISTENCE TEST ===")
saved_session_id = warranty_session
expected_before = [(m["role"], m["content"]) for m in store.list_messages(saved_session_id)]
del store
store2 = MemoryStore(DB)
after = [(m["role"], m["content"]) for m in store2.list_messages(saved_session_id)]
session_row = store2.get_session(saved_session_id)
print(f"  session survived restart (store re-opened on same file): {session_row is not None}")
print(f"  messages recovered: {len(after)}  match before restart: {after == expected_before}")
print(f"  recovered: {after}")