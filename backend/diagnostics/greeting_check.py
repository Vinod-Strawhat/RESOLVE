import os
import threading
import time

from dotenv import load_dotenv

load_dotenv()

from backend.agent.resolve_agent import build_resolve_agent
from backend.services.conversation import load_session_history, to_agent_transcript
from backend.services.memory_store import MemoryStore, default_memory_db_path

print(f"OPENROUTER_API_KEY present: {'YES' if os.environ.get('OPENROUTER_API_KEY') else 'NO'}")
print(f"OPENROUTER_MODEL={os.environ.get('OPENROUTER_MODEL')}")

store = MemoryStore(default_memory_db_path())
session_id = store.create_session()

out: dict = {"tool_activity": []}


def _run() -> None:
    try:
        agent = build_resolve_agent(tool_activity=out["tool_activity"])
        store.save_message(session_id, "user", "Hello, how are you?")
        history = load_session_history(store, session_id)
        transcript = to_agent_transcript(history)
        out["started"] = time.time()
        result = agent(prompt=transcript)
        out["elapsed"] = time.time() - out["started"]
        out["stop_reason"] = result.stop_reason
        content = result.message
        blocks = content["content"] if isinstance(content, dict) else content.content
        parts = []
        for block in blocks:
            text = block.get("text") if isinstance(block, dict) else getattr(block, "text", None)
            if text:
                parts.append(text)
        out["response"] = " ".join(parts).strip()
        store.save_message(session_id, "assistant", out["response"])
    except Exception as exc:
        out["error"] = repr(exc)[:600]


thread = threading.Thread(target=_run, daemon=True)
head = time.time()
thread.start()
thread.join(90)
print(f"\nGREETING RESULT:")
if thread.is_alive():
    print("  HANG (no completion within 90s)")
elif "error" in out:
    print(f"  ERROR {out['error']}")
else:
    print(f"  COMPLETED in {out['elapsed']:.1f}s  stop_reason: {out['stop_reason']}")
    print(f"  response: {out['response']!r}")
    print(f"  tool_activity: {out['tool_activity']}  (expected [] for a greeting)")
print(f"  session_id: {session_id}")
print(f"  stored messages: {[(m['role'], m['content']) for m in store.list_messages(session_id)]}")