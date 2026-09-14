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

> **Status: early foundation phase.** Phases 5-7A-1 are implemented:
> a human-approval workflow with simulated action execution, AI response
> evaluation, an automatic follow-up loop (up to 3 follow-up attempts per case,
> then human intervention), and pluggable execution channels including a local
> SMTP relay (Mailpit-compatible) behind the same approval gate. Real email via
> AWS SES and other external integrations are not implemented yet; execution is
> simulated by default.

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

## Structured cases & documents (Phase 4)

The agent can build a **structured case record** for a conversation and
incorporate **uploaded documents** (`.txt`, `.md`, `.pdf`).

### Case record

When the user describes a concrete unresolved problem, the model can call
`create_case` (once per conversation) and later `update_case` as new facts
arrive (product, amount, purchase_date, seller, warranty_expiry,
rejection_reason, status, next_action). Cases live in the `cases` table of the
same SQLite database, linked to the conversation session.

When a case exists for a session, the chat endpoint injects the active case id
into the agent context so the model can keep the record up to date.

Fetch a case and its documents:

```http
GET /api/cases/{case_id}
```

```json
{
  "case": {
    "id": "adb15bc416d34a739860ddc57ac4befb",
    "session_id": "7366a43952a04cba868030405fa658ad",
    "category": "warranty",
    "title": "Rejected laptop warranty claim - screen failure",
    "amount": 48999.0,
    "...": "..."
  },
  "documents": [
    {
      "id": "3f1c...2b.txt",
      "case_id": "adb15bc416d34a739860ddc57ac4befb",
      "filename": "invoice.txt",
      "size_bytes": 128,
      "extracted_text": "ASUS Vivobook ..."
    }
  ]
}
```

### Document upload & analysis

```http
POST /api/cases/{case_id}/documents
Content-Type: multipart/form-data
```

- Supported types: `.txt`, `.md`, `.pdf` (max 2 MB).
- Plain text is decoded (utf-8/utf-16 with BOM/latin-1 fallback); PDF text is
  extracted with `pypdf`.
- Files are stored under `database/uploads/` (git-ignored) under generated
  names; the original client filename is never used for the disk path.
- Missing/invalid uploads return `400`; unknown case ids return `404`; the
  server's internal `storage_path` is never exposed in responses.
- After safe storage and extraction, the Strands agent receives the active case,
  the current case record, and the extracted text, and can call `update_case`
  with facts found in the document.

No OCR is performed: scanned/image-only PDFs are stored but reported as having
no readable text.

## Approvals, execution & evaluation (Phases 5-7A)

Actions are created in `pending_approval` status and are never executed without
explicit human approval.

```http
POST /api/cases/{case_id}/prepare-followup  # AI proposes a pending_approval action
POST /api/actions/{action_id}/approve      # approve (required before execution)
POST /api/actions/{action_id}/reject       # discard
POST /api/actions/{action_id}/execute      # execute via the configured channel (requires approval)
POST /api/cases/{case_id}/evaluate-response  # AI response evaluation
POST /api/cases/{case_id}/evaluate           # deterministic manual evaluation
```

- Actions are created by the follow-up planner (`prepare-followup`); the server
  provides no endpoint to create an action directly and the planner itself is
  read-only and only ever returns a proposal.
- `execute` routes the action through the configured execution channel
  (simulated by default — see "Execution channels"), records the delivery
  reference and result on the action, and moves the case to
  `awaiting_response`.
- If the channel fails to deliver, the action is recorded as `failed` and the
  case is left untouched; it may be retried safely.
- A company response can then be recorded and evaluated.

## Automatic follow-up loop (Phase 6C)

When an AI evaluation decides the case still needs follow-up (status
`needs_follow_up`), RESOLVE can continue working toward resolution in a
repeatable loop:

1. **Prepare:** `POST /api/cases/{case_id}/prepare-followup` asks the follow-up
   planner (a read-only Strands agent) to suggest the next concrete action.
2. **Approve:** the suggestion is stored as a `pending_approval` action and
   shown in the UI; a human must approve it (execution is never automatic).
3. **Execute:** approving runs the same simulated executor, moving the case back
   to `awaiting_response`.
4. **Evaluate:** recording the next company response and running the AI
   evaluator again can either resolve the case, keep looping, or flag it for
   human intervention.

- The backend enforces a **maximum of 3 follow-up attempts per case**
  (configurable via the `MAX_FOLLOWUPS` environment variable). When the limit
  is reached, the next `needs_follow_up` evaluation forces
  `human_intervention` and no further follow-up actions are prepared.
- The follow-up planner is strictly read-only: it never modifies case state and
  never creates or executes actions; the server records every attempt in a
  dedicated `followup_attempts` table.
- `GET /api/cases/{case_id}/followup-status` reports the current attempt count
  and whether another follow-up action is still allowed.

## Execution channels (Phase 7A-1)

Action execution is pluggable through a small `Channel` protocol
(`backend/channels/base.py`). The channel is only ever invoked by
`ActionExecutor` after an action is `approved`; the human-approval model and
the state machine are unchanged.

- **Simulated (default):** `EXECUTION_CHANNEL=simulated` (or unset). Records a
  `RESOLVE-ACTION-*` reference; nothing is sent anywhere.
- **Local SMTP relay:** `EXECUTION_CHANNEL=smtp` sends a plain-text email
  through a local relay such as Mailpit (`backend/channels/smtp.py`). Requires
  `SMTP_HOST`, `SMTP_FROM`, and `SMTP_TO`; `SMTP_PORT` defaults to 1025 and
  `SMTP_USERNAME`/`SMTP_PASSWORD`/`SMTP_STARTTLS` are optional. The recipient
  comes ONLY from `SMTP_TO` - never from the model's free-text `target` field.
- Unknown `EXECUTION_CHANNEL` values and missing SMTP configuration **fail
  closed**: they never silently fall back to simulated.

The running channel is reported at `GET /api/config/execution`
(`{"channel": "...", "real_sending_enabled": bool}`); the response contains no
hosts, recipients, or credentials. The UI shows the active channel and, when
SMTP is active, requires an explicit confirmation before executing an approved
action.

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
│   ├── tools/     # Strands @tool definitions (create_case_note, create_case, update_case)
│   ├── services/  # note store + SQLite (memory, cases, documents) + extraction
│   └── main.py    # FastAPI entrypoint (/api/agent/chat, /api/cases, /health)
├── frontend/      # React + Vite app
├── database/      # SQLite runtime files + uploaded documents (git-ignored)
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
- **Phase 4 (done):** structured case records (SQLite `cases` table, `create_case`
  and `update_case` tools, active-case injection into chat) and document
  ingestion (safe `.txt`/`.md`/`.pdf` upload, `pypdf` text extraction, and
  Strands-based document analysis against the case record).
- **Phase 5 (done):** actions & approvals - SQLite `actions` table, action
  CRUD, and an explicit approve/reject workflow. No action executes without
  human approval.
- **Phase 6A (done):** simulated execution - `execute` runs without external
  side effects, records a `RESOLVE-ACTION-*` reference, and moves the case to
  `awaiting_response`.
- **Phase 6B (done):** response evaluation - record company responses
  (`POST /api/cases/{case_id}/responses`), deterministic manual evaluation, and
  an AI evaluator (`POST /api/cases/{case_id}/evaluate-response`) that returns
  `resolved`, `needs_follow_up`, or `human_intervention`.
- **Phase 6C (done):** automatic follow-up loop - read-only AI follow-up
  planner, backend-enforced maximum of 3 follow-up attempts (configurable via
  `MAX_FOLLOWUPS`), preparation + approval + simulated execution + re-evaluation
  cycle, and forced `human_intervention` once the limit is reached.
- **Phase 7A-1 (done):** pluggable execution channels - `Channel` protocol,
  simulated channel extracted to `backend/channels/simulated.py`, and a local
  SMTP relay channel (`backend/channels/smtp.py`) selected via
  `EXECUTION_CHANNEL`; atomic single-flight `begin_execution`,
  `execution_channel` persistence, `GET /api/config/execution`, and a
  frontend confirmation step before any real-channel send.

AWS SES (a real external email channel) and any AgentCore/AWS deployment belong
to **later phases** and are deliberately not implemented yet. No OCR is
performed on scanned documents.