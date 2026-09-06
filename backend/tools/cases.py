import json

from strands import tool
from strands.types.tools import ToolContext

from backend.services.case_store import CaseStore, get_case_store


def _resolve_session(tool_context: ToolContext) -> str | None:
    invocation_state = tool_context.invocation_state or {}
    return invocation_state.get("session_id")


def _store() -> CaseStore:
    return get_case_store()


@tool(context=True)
def create_case(
    tool_context: ToolContext,
    title: str,
    category: str,
    description: str,
    product: str | None = None,
) -> str:
    """Create a new structured case record for the current conversation.

    Use this when the user describes a concrete unresolved consumer problem
    (warranty dispute, refund, return) so it becomes a persisted, structured
    case. Only call it once per conversation; afterwards use update_case.

    Args:
        title: Short case title (e.g. "Rejected laptop warranty claim").
        category: Domain of the problem, e.g. "warranty", "refund", "return".
        description: Summary of the problem and what happened.
        product: Optional product involved (e.g. "ASUS Vivobook").

    Returns:
        A JSON string describing the created case or an error message.
    """
    session_id = _resolve_session(tool_context)
    if not session_id:
        return '{"status": "error", "message": "no active session for case creation"}'
    if not (title and title.strip() and category and category.strip() and description and description.strip()):
        return '{"status": "error", "message": "title, category and description must not be empty"}'
    try:
        case = _store().create_case(
            session_id,
            title=title.strip(),
            category=category.strip(),
            description=description.strip(),
            product=product.strip() if product else None,
        )
    except ValueError as exc:
        return json.dumps({"status": "error", "message": str(exc)})
    return json.dumps({"status": "created", **case})


@tool(context=True)
def update_case(
    tool_context: ToolContext,
    case_id: str,
    updates: dict[str, str],
) -> str:
    """Update one or more fields of an existing structured case.

    Use this when the user (or a document) provides new case facts such as
    product, amount, purchase_date, seller, warranty_expiry, rejection_reason,
    status, or next_action. Do not call it before a case exists.

    Args:
        case_id: The id of the case to update.
        updates: Mapping of case field name to new value. Allowed fields:
            category, title, description, product, amount, purchase_date,
            seller, warranty_expiry, rejection_reason, status, next_action.

    Returns:
        A JSON string describing the update result and updated case.
    """
    if not case_id or not case_id.strip():
        return '{"status": "error", "message": "case_id must not be empty"}'
    if not updates:
        return '{"status": "error", "message": "updates must not be empty"}'
    try:
        updated = _store().update_case(case_id.strip(), {str(k): str(v) for k, v in updates.items()})
    except ValueError as exc:
        return json.dumps({"status": "error", "message": str(exc)})
    return json.dumps({"status": "updated", "case_id": case_id, "updated_case": updated})