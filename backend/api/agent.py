import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.agent.model import AgentConfigError
from backend.agent.resolve_agent import build_resolve_agent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agent", tags=["agent"])


class AgentChatRequest(BaseModel):
    message: str = Field(min_length=1)


class ToolActivity(BaseModel):
    tool: str
    status: str


class AgentChatResponse(BaseModel):
    response: str
    tool_activity: list[ToolActivity]


def _get(block: object, key: str):
    if isinstance(block, dict):
        return block.get(key)
    return getattr(block, key, None)


@router.post("/chat", response_model=AgentChatResponse)
def chat(request: AgentChatRequest) -> AgentChatResponse:
    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="message must not be empty")

    tool_activity: list[dict] = []
    try:
        agent = build_resolve_agent(tool_activity=tool_activity)
    except AgentConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    try:
        result = agent(prompt=message)
    except Exception:
        logger.exception("RESOLVE agent invocation failed")
        raise HTTPException(
            status_code=502, detail="Agent invocation failed. Please try again."
        ) from None

    content = result.message
    if content is None:
        return AgentChatResponse(response="", tool_activity=[])
    content_block_list = content["content"] if isinstance(content, dict) else content.content

    text_parts = []
    for block in content_block_list:
        text = _get(block, "text")
        if text:
            text_parts.append(text)

    return AgentChatResponse(
        response=" ".join(text_parts).strip(),
        tool_activity=[ToolActivity(**item) for item in tool_activity],
    )