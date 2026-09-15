"""Agent chat endpoint (Phase 8B: authentication + session ownership)."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.agent.model import AgentConfigError
from backend.agent.resolve_agent import build_resolve_agent
from backend.api.dependencies import get_current_user, require_same_origin
from backend.services.case_store import get_case_store
from backend.services.conversation import load_session_history, to_agent_transcript
from backend.services.memory_store import get_memory_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agent", tags=["agent"])


class AgentChatRequest(BaseModel):
    session_id: str | None = Field(default=None, max_length=64)
    message: str = Field(min_length=1)


class ToolActivity(BaseModel):
    tool: str
    status: str


class AgentChatResponse(BaseModel):
    session_id: str
    case_id: str | None = None
    response: str
    tool_activity: list[ToolActivity]


def _get(block: object, key: str):
    if isinstance(block, dict):
        return block.get(key)
    return getattr(block, key, None)


def _session_or_404(store, session_id: str, user_id: str) -> dict:
    """Return the session metadata only if it belongs to ``user_id``.

    Missing and foreign sessions are indistinguishable (404) so a logged-in
    user cannot probe another user's session ids.
    """
    session = store.get_session(session_id)
    if session is None or session.get("user_id") != user_id:
        raise HTTPException(status_code=404, detail="session not found")
    return session


@router.post("/chat", response_model=AgentChatResponse)
def chat(
    request: AgentChatRequest,
    user: dict = Depends(get_current_user),
    _same_origin: None = Depends(require_same_origin),
) -> AgentChatResponse:
    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="message must not be empty")

    tool_activity: list[dict] = []
    try:
        agent = build_resolve_agent(tool_activity=tool_activity)
    except AgentConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    store = get_memory_store()

    if request.session_id is None:
        session_id = store.create_session(user_id=user["id"])
    else:
        session_id = request.session_id.strip()
        if not session_id:
            raise HTTPException(status_code=400, detail="session_id must not be blank")
        _session_or_404(store, session_id, user["id"])

    store.save_message(session_id=session_id, role="user", content=message)
    history = load_session_history(store, session_id)
    transcript = to_agent_transcript(history)

    case = get_case_store().get_case_by_session(session_id)
    if case is not None:
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

    try:
        result = agent(
            prompt=transcript,
            invocation_state={"session_id": session_id, "user_id": user["id"]},
        )
    except Exception:
        logger.exception("RESOLVE agent invocation failed")
        raise HTTPException(
            status_code=502, detail="Agent invocation failed. Please try again."
        ) from None

    content = result.message
    if content is None:
        response_text = ""
    else:
        content_block_list = content["content"] if isinstance(content, dict) else content.content
        text_parts = []
        for block in content_block_list:
            text = _get(block, "text")
            if text:
                text_parts.append(text)
        response_text = " ".join(text_parts).strip()

    store.save_message(session_id=session_id, role="assistant", content=response_text)

    active_case = get_case_store().get_case_by_session(session_id)
    return AgentChatResponse(
        session_id=session_id,
        case_id=active_case["id"] if active_case else None,
        response=response_text,
        tool_activity=[ToolActivity(**item) for item in tool_activity],
    )