import json

from strands import tool
from strands.types.tools import ToolContext

from backend.services.action_store import ACTION_TYPES, ActionStore, get_action_store
from backend.services.case_store import CaseStore, get_case_store


def _resolve_session(tool_context: ToolContext) -> str | None:
    invocation_state = tool_context.invocation_state or {}
    return invocation_state.get("session_id")


def _case_store() -> CaseStore:
    return get_case_store()


def _store() -> ActionStore:
    return get_action_store()


def _allowed_types() -> str:
    return ", ".join(ACTION_TYPES)


@tool(context=True)
def prepare_action(
    tool_context: ToolContext,
    type: str,
    title: str,
    reason: str,
    content: str,
    target: str = "",
) -> str:
    """Prepare a concrete next action for the active case so a human can review and approve it.

    Call this only when the case has enough evidence to justify a specific
    action (e.g. escalating a rejected warranty claim to the seller's support
    team). The action is stored for review; it is NOT sent or executed. It
    awaits human approval. Do not call it when critical information is missing,
    and never invent facts that are not present in the conversation or documents.

    Args:
        type: One of: warranty_dispute, refund_request, return_request, escalation, other.
        title: Short human-readable title for the action.
        reason: Why this action is recommended, based only on known case facts.
        content: The prepared message or request text. Use only information
            actually known about the case; do not invent missing facts.
        target: Optional recipient or channel, e.g. "ASUS Support".

    Returns:
        A JSON string describing the prepared action awaiting approval, or an
        error message.
    """
    session_id = _resolve_session(tool_context)
    if not session_id:
        return '{"status": "error", "message": "no active session for action preparation"}'

    case = _case_store().get_case_by_session(session_id)
    if case is None:
        return '{"status": "error", "message": "no active case; create a case before preparing an action"}'

    if type not in ACTION_TYPES:
        return json.dumps(
            {
                "status": "error",
                "message": f"type must be one of: {_allowed_types()}",
            }
        )
    if not (title and title.strip() and reason and reason.strip() and content and content.strip()):
        return '{"status": "error", "message": "title, reason and content must not be empty"}'

    try:
        action = _store().create_action(
            case["id"],
            type=type.strip(),
            target=(target or "").strip(),
            title=title.strip(),
            reason=reason.strip(),
            content=content.strip(),
        )
        action = _store().submit_for_approval(action["id"])
    except ValueError as exc:
        return json.dumps({"status": "error", "message": str(exc)})

    return json.dumps(
        {
            "status": "prepared",
            "action_id": action["id"],
            "case_id": action["case_id"],
            "type": action["type"],
            "target": action["target"],
            "title": action["title"],
            "reason": action["reason"],
            "approval_status": action["status"],
            "note": "This action is prepared for human review and will not be "
            "sent or executed until approved.",
        }
    )