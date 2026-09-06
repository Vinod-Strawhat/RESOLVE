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

> **Status: early foundation phase.** None of the above agent behavior is
> implemented yet. This repository currently contains only the project skeleton,
> dependency configuration, and a minimal FastAPI/React foundation.

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
│   ├── agent/     # Strands agent (later phase)
│   ├── tools/     # Agent tools (later phase)
│   ├── models/    # Pydantic domain models (later phase)
│   ├── services/  # Business logic / integrations (later phase)
│   └── main.py    # FastAPI entrypoint (health/no-op endpoints only)
├── frontend/      # React + Vite app
├── database/      # SQLite runtime files (schema comes later)
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
API keys. Placeholders exist for OpenRouter credentials that will be used in a
later phase.

## Roadmap

- **Phase 1 (current):** project foundation - structure, dependencies, minimal
  FastAPI app, React + Vite app, SQLite directory, env/git hygiene.
- **Phase 2 (planned):** SQLite case schema and the Strands agent workflow
  (model through OpenRouter, state persistence, tooling), then document
  ingestion and case analysis.

All agent behavior, document analysis, warranty reasoning, automated follow-ups,
approval workflows, and any AgentCore/AWS deployment belong to **later phases**
and are deliberately not implemented yet.