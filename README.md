# RESOLVE

**Don't just tell me what to do. Work toward resolving the problem.**

RESOLVE is an AI agent that takes an unresolved consumer problem and works toward
resolving it end-to-end. It is being built for the **Agents for Humans** hackathon
(**Everyday Agents** track).

## What RESOLVE does

Given a real consumer dispute - such as a rejected product return, a missing
refund, or a warranty claim that a company refused - RESOLVE will eventually:

1. Understand the case.
2. Analyze provided evidence and documents (invoices, warranty info, company responses).
3. Identify relevant facts, deadlines, missing information, and issues.
4. Build a case timeline.
5. Determine the next appropriate action.
6. Prepare an action or message.
7. Ask the human for approval when a consequential action requires it.
8. Execute the approved action.
9. Wait, remember the case, and follow up when appropriate.
10. Continue until the case is resolved or human intervention is required.

> **Status: early foundation phase.** Phase 2 (Strands agent tool-calling loop)
> and Phase 3 (persistent conversation memory) are implemented. Case documents,
> email, approvals, and autonomous follow-ups are not implemented yet.

## Conversation memory (Phase 3)

`POST /api/agent/chat` maintains a persistent, multi-turn conversation.

- A new conversation starts by omitting `session_id`; the API creates a session
  and returns its `session_id`.
- Send the returned `session_id` back with later messages to continue the same
  conversation.
- History is stored in SQLite at `database/resolve.db` (git-ignored), so
  conversations survive backend restarts.
- The Strands agent receives the stored transcript so it can understand
  follow-up messages; the system prompt instructs it not to re-ask for
  information the user already provided.

Example request:

```json
{
  "message": "My laptop warranty claim was rejected."
}
```

Example response:

```json
{
  "session_id": "2f5c9a0e8d1b4f6a9c3e7b2d5a8f0c1e",
  "response": "I've recorded your case. What laptop model and purchase date?",
  "tool_activity": [
    {
      "tool": "create_case_note",
      "status": "executed"
    }
  ]
}
```

Continue the conversation:

```json
{
  "session_id": "2f5c9a0e8d1b4f6a9c3e7b2d5a8f0c1e",
  "message": "It's an ASUS Vivobook. I bought it in March 2026."
}
```

An unknown or blank `session_id` returns `404 session not found`. Only user
messages and assistant responses are stored; tool internals and model reasoning
are not persisted.

## Current MVP scope

The MVP deliberately targets a narrow domain:

- Product returns
- Refunds
- Warranty disputes

## Technology direction

| Area            | Choice                                             |
| --------------- | -------------------------------------------------- |
| Frontend        | React + Vite (case-management interface)           |
| Backend         | Python / FastAPI                                   |
| Agent framework | Strands Agents SDK                                 |
| Model gateway   | OpenRouter (Strands has a first-party OpenRouter integration) |
| Persistence     | SQLite (initial)                                   |
| Cloud           | AWS only where it provides genuine value           |

## Repository layout

```
RESOLVE/
├── backend/
│   ├── agent/     # Strands agent (system prompt, tools, OpenRouter model)
│   ├── tools/     # Strands @tool definitions (create_case_note)
│   ├── services/  # note store + SQLite conversation memory + transcript helper
│   └── main.py    # FastAPI entrypoint (/api/agent/chat, /health)
├── frontend/      # React + Vite app
├── database/      # SQLite runtime files (resolve.db, git-ignored)
├── tests/         # pytest suite
├── docs/          # Design docs
├── .env.example
└── ...
```

## Getting started (Phase 1)

### Backend

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements-dev.txt
uvicorn backend.main:app --reload --port 8000
```

Health check: `http://localhost:8000/health`

### Frontend

```powershell
cd frontend
npm install
npm run dev
```

### Tests

```powershell
python -m pytest
```

## Configuration

Copy `.env.example` to `.env` and fill in values locally. Do not commit real
API keys.

## Roadmap

- **Phase 1 (done):** project foundation - structure, dependencies, minimal
  FastAPI app, React + Vite app, SQLite directory, env/git hygiene.
- **Phase 2 (done):** Strands agent tool-calling loop - the model (through
  OpenRouter) independently selects and executes `create_case_note` and returns
  a final response.
- **Phase 3 (done):** persistent conversation memory - SQLite-backed sessions
  and messages with multi-turn Strands context.
- **Phase 4 (planned):** case-management features such as document ingestion,
  case analysis, and generated next actions.

Automated follow-ups, approval workflows, email, and any AgentCore/AWS
deployment belong to **later phases** and are deliberately not implemented yet.