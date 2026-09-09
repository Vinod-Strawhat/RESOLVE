"""AI-powered follow-up action preparation (Phase 6C).

When a case needs follow-up, this service asks the LLM to suggest the next
concrete action grounded in the available case facts, response history,
previous actions, and evaluations.  The model NEVER modifies case state;
it only returns a structured recommendation that the caller stores as a
pending-approval action through the action store.

Safety:
- The preparer is read-only: no database writes, no external calls.
- All model output is validated before storage.
- Malformed output raises ValueError; no action is created.
- No inventing facts, dates, approvals, or external communications.
"""

import json
import logging
import re
from dataclasses import dataclass

from pydantic import BaseModel, Field, ValidationError

from backend.agent.model import build_model
from backend.services.action_store import ACTION_TYPES

logger = logging.getLogger(__name__)

PREPARER_SYSTEM_PROMPT = """\
You are a follow-up action planner for a consumer support case resolver.
Your ONLY job is to read the supplied case data, response history, previous
actions, and evaluations, then recommend ONE concrete follow-up action.

You must return a JSON object with exactly these fields:

{
  "type": "<one of: warranty_dispute, refund_request, return_request, escalation, other>",
  "title": "<short human-readable title for the action>",
  "reason": "<one or two sentences explaining why this action is recommended>",
  "content": "<the prepared message or request text>",
  "target": "<optional recipient or channel, e.g. 'ASUS Support'>"
}

RULES:
1. Base your recommendation ONLY on the case facts, responses, actions, and
   evaluations provided.  Do NOT invent facts, dates, approval numbers,
   refund amounts, rejection reasons, or any external actions.
2. Distinguish clearly:
   - Known facts (explicitly stated in case fields or documents)
   - Support claims (stated in response content)
   - Model inference (your reasonable deduction from the above)
3. The action content must use only information actually present in the case
   data.  Do not fabricate communications that were sent.
4. Choose a type that matches the action purpose.
5. The reason must reference specific case facts, not generic advice.
6. If you cannot determine a safe next step, use type "human_intervention"
   and explain why in the reason field.
7. Return ONLY the JSON object.  No other text."""


# --- Structured output schema ---


class PreparedAction(BaseModel):
    """Pydantic schema for the preparer's structured output."""

    type: str = Field(description="Action type from the allowed set")
    title: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    content: str = Field(min_length=1)
    target: str = Field(default="")


@dataclass(frozen=True)
class PreparedActionResult:
    """Safe prepared action data exposed to the API / caller."""

    type: str
    title: str
    reason: str
    content: str
    target: str


# --- Context building ---


def build_followup_context(
    case: dict,
    responses: list[dict],
    actions: list[dict],
    followup_history: list[dict],
    followup_count: int,
) -> str:
    """Build a deterministic context string for the preparer model."""
    case_lines = []
    for key in (
        "id",
        "category",
        "title",
        "description",
        "product",
        "amount",
        "purchase_date",
        "seller",
        "warranty_expiry",
        "rejection_reason",
        "status",
        "next_action",
    ):
        val = case.get(key)
        if val is not None and val != "":
            case_lines.append(f"- {key}: {val}")
    case_text = "\n".join(case_lines) if case_lines else "(no structured case fields)"

    response_parts = []
    for i, resp in enumerate(responses, 1):
        response_parts.append(
            f"Response {i} [{resp.get('source', 'unknown')}] "
            f"({resp.get('received_at', '?')}):\n{resp.get('content', '')}"
        )
    history_text = "\n\n".join(response_parts) if response_parts else "(no responses)"

    action_parts = []
    for i, act in enumerate(actions, 1):
        status = act.get("status", "?")
        exec_result = act.get("execution_result") or ""
        exec_error = act.get("execution_error") or ""
        detail = f"  status: {status}"
        if exec_result:
            detail += f"\n  result: {exec_result}"
        if exec_error:
            detail += f"\n  error: {exec_error}"
        action_parts.append(
            f"Action {i}: {act.get('title', '?')} (type: {act.get('type', '?')})\n{detail}"
        )
    actions_text = "\n\n".join(action_parts) if action_parts else "(no previous actions)"

    eval_parts = []
    for i, ev in enumerate(followup_history, 1):
        eval_parts.append(
            f"Follow-up evaluation {i}: attempt #{ev.get('attempt_number', '?')}\n"
            f"  reason: {ev.get('evaluation_reason', '?')}\n"
            f"  confidence: {ev.get('evaluation_confidence', '?')}"
        )
    evals_text = "\n\n".join(eval_parts) if eval_parts else "(no previous follow-up evaluations)"

    return (
        f"=== CASE DETAILS ===\n{case_text}\n\n"
        f"=== RESPONSE HISTORY ({len(responses)} total) ===\n{history_text}\n\n"
        f"=== PREVIOUS ACTIONS ({len(actions)} total) ===\n{actions_text}\n\n"
        f"=== PREVIOUS FOLLOW-UP EVALUATIONS ({len(followup_history)} total) ===\n{evals_text}\n\n"
        f"=== CONTEXT ===\n"
        f"Current case status: {case.get('status', 'unknown')}\n"
        f"Follow-up attempt number: {followup_count}\n"
    )


# --- Validation ---


def validate_prepared_action(data: dict) -> PreparedActionResult:
    """Validate raw model output into a safe PreparedActionResult.

    Raises ValueError on any validation failure.
    """
    try:
        result = PreparedAction(**data)
    except ValidationError as exc:
        raise ValueError(f"invalid prepared action output: {exc}") from exc

    action_type = result.type.strip()
    if action_type not in ACTION_TYPES:
        raise ValueError(
            f"invalid action type {action_type!r}; "
            f"allowed: {', '.join(ACTION_TYPES)}"
        )

    title = result.title.strip()
    reason = result.reason.strip()
    content = result.content.strip()
    if not title:
        raise ValueError("invalid prepared action: title must not be empty")
    if not reason:
        raise ValueError("invalid prepared action: reason must not be empty")
    if not content:
        raise ValueError("invalid prepared action: content must not be empty")

    return PreparedActionResult(
        type=action_type,
        title=title,
        reason=reason,
        content=content,
        target=result.target.strip(),
    )


def _extract_json(text: str) -> dict:
    """Defensively extract a JSON object from model text output."""
    text = text.strip()
    if text.startswith("{"):
        return json.loads(text)

    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if fence_match:
        return json.loads(fence_match.group(1).strip())

    brace_match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if brace_match:
        return json.loads(brace_match.group(0))

    raise ValueError(f"no JSON object found in model output: {text[:200]!r}")


# --- Main preparer ---


def prepare_followup_action(
    case_store,
    response_store,
    action_store,
    followup_store,
    case_id: str,
    model=None,
    agent=None,
) -> PreparedActionResult:
    """Prepare a follow-up action suggestion using the Strands agent.

    Returns a PreparedActionResult on success.  Raises ValueError on any
    failure.  Never modifies case state or creates actions.
    """
    case = case_store.get_case(case_id)
    if case is None:
        raise ValueError(f"case not found: {case_id}")

    if case.get("status") != "needs_follow_up":
        raise ValueError(
            f"case in status {case.get('status')!r} cannot prepare follow-up; "
            "must be needs_follow_up"
        )

    responses = response_store.list_responses_for_case(case_id)
    actions = action_store.list_actions_for_case(case_id)
    followup_count = followup_store.get_followup_count(case_id)
    followup_history = followup_store.get_followup_history(case_id)

    context = build_followup_context(
        case, responses, actions, followup_history, followup_count
    )

    prompt = (
        "Based on the case context below, recommend ONE concrete follow-up "
        "action.  Return ONLY a JSON object with: type, title, reason, "
        "content, target.\n\n"
        f"{context}"
    )

    if agent is None:
        if model is None:
            model = build_model()

        from strands import Agent

        agent = Agent(
            model=model,
            system_prompt=PREPARER_SYSTEM_PROMPT,
            tools=[],
        )

    result = agent(prompt)

    raw_text = ""
    content_obj = result.message
    if content_obj is not None:
        if isinstance(content_obj, dict):
            blocks = content_obj.get("content", [])
        else:
            blocks = content_obj.content if hasattr(content_obj, "content") else []
        for block in blocks:
            text_val = block.get("text") if isinstance(block, dict) else getattr(block, "text", None)
            if text_val:
                raw_text += text_val

    if not raw_text.strip():
        raise ValueError("model returned empty response")

    try:
        data = _extract_json(raw_text)
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"failed to parse model output: {exc}") from exc

    return validate_prepared_action(data)
