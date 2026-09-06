import json
from dotenv import load_dotenv

load_dotenv()

from backend.agent.resolve_agent import build_resolve_agent

agent = build_resolve_agent()
result = agent(prompt="My laptop warranty claim was rejected because the company says the damage is not covered.")

message = result.message
print("=== message type:", type(message).__name__)
content = message["content"] if isinstance(message, dict) else message.content
print("=== num blocks:", len(content))
for i, block in enumerate(content):
    if isinstance(block, dict):
        kind = [k for k in ("text", "toolUse", "toolResult", "role") if k in block]
        print(f"--- block {i} dict, fields={kind}")
        if "toolUse" in block:
            print("TOOLUSE:", json.dumps(block["toolUse"], default=str)[:800])
        if "toolResult" in block:
            print("TOOLRESULT:", json.dumps(block["toolResult"], default=str)[:800])
        if "text" in block:
            print("TEXT:", str(block["text"])[:200])
    else:
        print(f"--- block {i} {type(block).__name__}:", str(block)[:300])

print("=== stop_reason:", result.stop_reason)