from strands import Agent
from strands.hooks.events import AfterToolCallEvent

from backend.agent.model import build_model
from backend.agent.prompts import RESOLVE_SYSTEM_PROMPT
from backend.tools.actions import prepare_action
from backend.tools.case_notes import create_case_note
from backend.tools.cases import create_case, update_case

RESOLVE_TOOLS = [create_case_note, create_case, update_case, prepare_action]


def _make_tool_recorder(target: list[dict]):
    def on_after_tool_call(event: AfterToolCallEvent) -> None:
        status = "executed" if event.result["status"] == "success" else "failed"
        target.append({"tool": event.tool_use["name"], "status": status})

    return on_after_tool_call


def build_resolve_agent(tool_activity: list[dict] | None = None) -> Agent:
    hooks = []
    if tool_activity is not None:
        hooks.append(_make_tool_recorder(tool_activity))
    return Agent(
        model=build_model(),
        system_prompt=RESOLVE_SYSTEM_PROMPT,
        tools=list(RESOLVE_TOOLS),
        hooks=hooks,
    )