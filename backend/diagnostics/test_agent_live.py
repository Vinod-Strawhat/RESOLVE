import json
import os
import threading
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

api_key_present = bool(os.environ.get("OPENROUTER_API_KEY"))
print(f"OPENROUTER_API_KEY present: {'YES' if api_key_present else 'NO'}")
print(f"OPENROUTER_MODEL={os.environ.get('OPENROUTER_MODEL')}")

from backend.agent.resolve_agent import build_resolve_agent

state = {}


def run():
    try:
        agent = build_resolve_agent(tool_activity=state_tool_activity)
        state["started"] = time.time()
        result = agent(prompt=state["message"])
        state["result"] = result
        state["elapsed"] = time.time() - state["started"]
    except Exception as exc:
        state["error"] = repr(exc)
        state["elapsed"] = time.time() - state.get("started", time.time())


state_tool_activity: list[dict] = []


def invoke(message: str) -> None:
    state.clear()
    state_tool_activity.clear()
    state["message"] = message
    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(90)
    if t.is_alive():
        print(f"RESULT: HANG (no completion within 90s) message={message!r}")
        return
    if "error" in state:
        print(f"RESULT: ERROR after {state['elapsed']:.1f}s: {state['error'][:500]}")
        return
    result = state["result"]
    elapsed = state["elapsed"]
    message_obj = result.message
    content = message_obj["content"] if isinstance(message_obj, dict) else message_obj.content
    texts = []
    for block in content:
        if isinstance(block, dict) and block.get("text"):
            texts.append(block["text"])
        else:
            text = getattr(block, "text", None)
            if text:
                texts.append(text)
    print(f"RESULT: COMPLETED in {elapsed:.1f}s")
    print(f"  stop_reason: {result.stop_reason}")
    print(f"  response: {' '.join(texts).strip()!r}")
    print(f"  tool_activity: {state_tool_activity}")


notes_path = Path(__file__).resolve().parents[2] / "database" / "case_notes.json"
before = notes_path.read_text(encoding="utf-8") if notes_path.exists() else ""

print("\n--- DIRECT STRANDS TEST (warranty) ---")
invoke("My laptop warranty claim was rejected because the company says the damage is not covered.")
time.sleep(10)

print("\n--- DIRECT STRANDS TEST (greeting) ---")
invoke("Hello, how are you?")
time.sleep(10)

print("\n--- DIRECT STRANDS TEST (refund) ---")
invoke("The seller rejected my refund request and said I need to provide proof of purchase.")

print("\n--- PERSISTENCE CHECK ---")
if notes_path.exists():
    after = notes_path.read_text(encoding="utf-8")
    print(f"case_notes.json exists, size={len(after)} bytes")
    try:
        records = json.loads(after)
        new_records = [r for r in records if json.dumps(r) not in (json.dumps(b) for b in json.loads(before or '[]'))]
        print(f"total records: {len(records)}")
    except Exception as exc:
        print(f"could not parse: {exc}")
else:
    print("case_notes.json does not exist")