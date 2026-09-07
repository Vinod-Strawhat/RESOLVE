"""AI-powered response evaluation service (Phase 6B-2).

The evaluator reads the case, response history, and latest response, then
asks the LLM to produce a structured recommendation (resolved / needs_follow_up
/ human_intervention).  The model NEVER modifies case state directly; it only
returns a validated result that the caller applies through the state machine.

Safety:
- The evaluator is read-only: no tools, no database writes, no external calls.
- All model output is validated before any state transition.
- Model failures leave the case untouched and surface a safe error.
"""

import json
import logging
import re
from dataclasses import dataclass

from pydantic import BaseModel, Field, ValidationError

from backend.agent.model import build_model
from backend.services.action_store import get_action_store
from backend.services.case_store import EVALUATION_OUTCOMES

logger = logging.getLogger(__name__)

EVALUATOR_SYSTEM_PROMPT = """\
You are a support-response evaluator.  Your ONLY job is to read the supplied
case and response data and decide the next resolution status.

You must return a JSON object with exactly these fields:

{
  "outcome": "resolved" | "needs_follow_up" | "human_intervention",
  "confidence": <float 0.0 to 1.0>,
  "reason": "<one or two sentences of concise reasoning>",
  "next_step": "<concrete next step the user or support should take>"
}

RULES:
1. Base your evaluation ONLY on the case facts and response content provided.
   Do NOT invent facts, dates, approval numbers, refund amounts, or any
   external actions.
2. Case facts are authoritative only when explicitly present in the case data.
   Response content is a claim by the support side — treat it as evidence, not
   established truth.
3. Distinguish clearly:
   - Known facts (explicitly stated in case fields or user-provided documents)
   - Support claims (stated in response content)
   - Model inference (your reasonable deduction from the above)
4. Use 'resolved' ONLY when the response provides credible evidence that the
   user's core problem has been addressed.
5. Use 'needs_follow_up' when the response requests information, promises
   future action without resolution, gives an incomplete answer, or when a
   clear next step exists for further communication.
6. Use 'human_intervention' when the situation is ambiguous, high-risk,
   involves repeated refusals without adequate explanation, requires
   legal/financial/escalation judgment, or you genuinely cannot determine
   the safe next step.  Do NOT choose this automatically just because
   information is missing.
7. Never claim a case is resolved without evidence.
8. Never invent a refund, approval, rejection, or any external action.

Return ONLY the JSON object.  No other text."""


# --- Structured output schema ---


class EvaluationResult(BaseModel):
    """Pydantic schema for the evaluator's structured output."""

    outcome: str = Field(
        description="One of: resolved, needs_follow_up, human_intervention",
    )
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(min_length=1)
    next_step: str = Field(min_length=1)


# --- Public data class for API responses ---


@dataclass(frozen=True)
class EvaluationOutcome:
    """Safe evaluation result exposed to the API / frontend."""

    outcome: str
    confidence: float
    reason: str
    next_step: str


# --- Context building ---


def build_evaluation_context(case: dict, responses: list[dict]) -> str:
    """Build a deterministic text context for the evaluator model."""
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

    case_text = "\n".join(case_lines) if case_lines else "(no structured case fields recorded)"

    response_parts = []
    for i, resp in enumerate(responses, 1):
        response_parts.append(
            f"Response {i} [{resp.get('source', 'unknown')}] "
            f"({resp.get('received_at', '?')}):\n{resp.get('content', '')}"
        )

    history_text = "\n\n".join(response_parts) if response_parts else "(no responses recorded)"

    latest = responses[-1] if responses else None
    latest_text = latest.get("content", "") if latest else "(none)"
    latest_source = latest.get("source", "unknown") if latest else "unknown"

    is_followup = len(responses) > 1

    return (
        f"=== CASE DETAILS ===\n{case_text}\n\n"
        f"=== RESPONSE HISTORY ({len(responses)} total) ===\n{history_text}\n\n"
        f"=== LATEST RESPONSE (from: {latest_source}) ===\n{latest_text}\n\n"
        f"=== CONTEXT ===\n"
        f"Current case status: {case.get('status', 'unknown')}\n"
        f"Number of prior responses: {len(responses) - 1 if responses else 0}\n"
        f"This is a {'follow-up' if is_followup else 'first'} response.\n"
    )


# --- Validation ---


def validate_evaluation_result(data: dict) -> EvaluationOutcome:
    """Validate raw model output into a safe EvaluationOutcome.

    Raises ValueError on any validation failure.  Never returns partial data.
    """
    try:
        result = EvaluationResult(**data)
    except ValidationError as exc:
        raise ValueError(f"invalid evaluation output: {exc}") from exc

    if result.outcome not in EVALUATION_OUTCOMES:
        raise ValueError(
            f"invalid outcome {result.outcome!r}; "
            f"allowed: {', '.join(sorted(EVALUATION_OUTCOMES))}"
        )

    reason = result.reason.strip()
    next_step = result.next_step.strip()
    if not reason:
        raise ValueError("invalid evaluation output: reason must not be empty")
    if not next_step:
        raise ValueError("invalid evaluation output: next_step must not be empty")

    return EvaluationOutcome(
        outcome=result.outcome,
        confidence=round(result.confidence, 3),
        reason=reason,
        next_step=next_step,
    )


def _extract_json(text: str) -> dict:
    """Defensively extract a JSON object from model text output.

    Handles cases where the model wraps JSON in markdown fences or adds
    surrounding text.
    """
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


# --- Main evaluator ---


def evaluate_response(
    case_store,
    response_store,
    case_id: str,
    model=None,
    agent=None,
) -> EvaluationOutcome:
    """Evaluate a recorded support response using the Strands agent.

    Returns an EvaluationOutcome on success.  Raises ValueError on any failure
    (model error, invalid output, missing data).  Never modifies case state.

    ``model`` is a Strands model instance (defaults to the configured model).
    ``agent`` is an optional pre-built agent/callable for testing: it is called
    with the prompt and must return an object exposing ``.message``.
    """
    case = case_store.get_case(case_id)
    if case is None:
        raise ValueError(f"case not found: {case_id}")

    if case.get("status") != "response_received":
        raise ValueError(
            f"case in status {case.get('status')!r} cannot be evaluated; "
            "must be response_received"
        )

    responses = response_store.list_responses_for_case(case_id)
    if not responses:
        raise ValueError("no responses recorded for this case")

    context = build_evaluation_context(case, responses)

    prompt = (
        "Evaluate the following support case and response data.\n\n"
        f"{context}\n\n"
        "Return ONLY a JSON object with: outcome, confidence, reason, next_step."
    )

    if agent is None:
        if model is None:
            model = build_model()

        from strands import Agent

        agent = Agent(
            model=model,
            system_prompt=EVALUATOR_SYSTEM_PROMPT,
            tools=[],
        )

    result = agent(prompt)

    raw_text = ""
    content = result.message
    if content is not None:
        if isinstance(content, dict):
            blocks = content.get("content", [])
        else:
            blocks = content.content if hasattr(content, "content") else []
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

    return validate_evaluation_result(data)


# --- Singleton (for dependency injection in tests) ---

_evaluator_store_refs: dict = {}
_evaluator_lock = __import__("threading").Lock()


def set_evaluator_stores(case_store=None, response_store=None) -> None:
    """Override default stores for testing."""
    global _evaluator_store_refs
    with _evaluator_lock:
        _evaluator_store_refs = {}
        if case_store is not None:
            _evaluator_store_refs["case_store"] = case_store
        if response_store is not None:
            _evaluator_store_refs["response_store"] = response_store


def evaluate_response_default(case_id: str, model=None) -> EvaluationOutcome:
    """Convenience wrapper using default singleton stores."""
    from backend.services.case_store import get_case_store
    from backend.services.response_store import get_response_store

    cs = _evaluator_store_refs.get("case_store") or get_case_store()
    rs = _evaluator_store_refs.get("response_store") or get_response_store()
    return evaluate_response(cs, rs, case_id, model=model)