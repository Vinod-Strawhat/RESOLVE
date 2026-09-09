import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.services.case_store import (
    EVALUATION_OUTCOMES,
    get_case_store,
)
from backend.services.action_store import get_action_store
from backend.services.followup_preparer import (
    PreparedActionResult,
    prepare_followup_action,
)
from backend.services.followup_store import get_followup_store, get_max_followups
from backend.services.response_evaluator import (
    EvaluationOutcome,
    evaluate_response,
    validate_evaluation_result,
)
from backend.services.response_store import get_response_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/cases", tags=["case-responses"])

RESPONSEABLE_STATUSES = ("awaiting_response", "needs_follow_up")


class RecordResponseRequest(BaseModel):
    source: str
    content: str


class EvaluateRequest(BaseModel):
    outcome: str


def _case_or_404(case_id: str) -> dict:
    case = get_case_store().get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="case not found")
    return case


@router.post("/{case_id}/responses")
def record_response(case_id: str, request: RecordResponseRequest) -> dict:
    source = (request.source or "").strip()
    content = (request.content or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="response content must not be empty")
    if not source:
        raise HTTPException(status_code=400, detail="response source must not be empty")

    case = _case_or_404(case_id)
    if case["status"] not in RESPONSEABLE_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=(
                f"case in status {case['status']!r} cannot receive a response; "
                "must be awaiting_response or needs_follow_up"
            ),
        )

    response = get_response_store().create_response(
        case_id, source=source, content=content
    )
    updated = get_case_store().transition_status(case_id, "response_received")
    return {"response": response, "case": updated}


@router.get("/{case_id}/responses")
def list_responses(case_id: str) -> dict:
    _case_or_404(case_id)
    responses = get_response_store().list_responses_for_case(case_id)
    return {"case_id": case_id, "responses": responses}


@router.post("/{case_id}/evaluate")
def evaluate_case(case_id: str, request: EvaluateRequest) -> dict:
    outcome = (request.outcome or "").strip()
    if outcome not in EVALUATION_OUTCOMES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"invalid outcome {outcome!r}; allowed: "
                "resolved, needs_follow_up, human_intervention"
            ),
        )

    case = _case_or_404(case_id)
    if case["status"] != "response_received":
        raise HTTPException(
            status_code=409,
            detail=(
                f"case in status {case['status']!r} cannot be evaluated; "
                "must be response_received"
            ),
        )

    updated = get_case_store().transition_status(case_id, outcome)
    return {"case": updated}


@router.post("/{case_id}/evaluate-response")
def evaluate_response_ai(case_id: str) -> dict:
    """AI-powered response evaluation.

    Invokes the Strands evaluator to analyse the case and response history,
    then safely applies the resulting state transition through the machine.
    The model never modifies case state directly.  A ``needs_follow_up``
    outcome is recorded as a follow-up attempt and the configured maximum
    number of follow-ups is enforced server-side (exceeding it forces
    ``human_intervention``).
    """
    case_store = get_case_store()
    case = _case_or_404(case_id)

    if case["status"] != "response_received":
        raise HTTPException(
            status_code=409,
            detail=(
                f"case in status {case['status']!r} cannot be evaluated; "
                "must be response_received"
            ),
        )

    try:
        result: EvaluationOutcome = evaluate_response(
            case_store,
            get_response_store(),
            case_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"evaluation failed: {exc}",
        ) from exc
    except Exception as exc:
        logger.exception("unexpected evaluator error")
        raise HTTPException(
            status_code=500,
            detail="evaluation service error",
        ) from exc

    outcome = result.outcome
    followup_store = get_followup_store()
    max_followups = get_max_followups()
    followup_count = followup_store.get_followup_count(case_id)
    followup_used = False

    if outcome == "needs_follow_up":
        if followup_count >= max_followups:
            outcome = "human_intervention"
        else:
            followup_store.record_followup(
                case_id,
                reason=result.reason,
                confidence=result.confidence,
            )
            followup_count += 1
            followup_used = True

    try:
        updated = case_store.transition_status(case_id, outcome)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return {
        "evaluation": {
            "outcome": result.outcome,
            "confidence": result.confidence,
            "reason": result.reason,
            "next_step": result.next_step,
        },
        "followup": {
            "count": followup_count,
            "max_followups": max_followups,
            "overflowed_to_human_intervention": outcome == "human_intervention"
            and result.outcome == "needs_follow_up",
            "followup_used": followup_used,
        },
        "case": updated,
    }


@router.get("/{case_id}/followup-status")
def followup_status(case_id: str) -> dict:
    """Return follow-up attempt information for a case."""
    case = _case_or_404(case_id)
    followup_store = get_followup_store()
    count = followup_store.get_followup_count(case_id)
    max_followups = get_max_followups()
    return {
        "case_id": case_id,
        "case_status": case["status"],
        "followup_count": count,
        "max_followups": max_followups,
        "can_prepare_action": case["status"] == "needs_follow_up"
        and count < max_followups,
        "attempts": followup_store.get_followup_history(case_id),
    }


@router.post("/{case_id}/prepare-followup")
def prepare_followup(case_id: str) -> dict:
    """Prepare the next follow-up action for a case awaiting follow-up.

    The AI only recommends the action.  The backend validates the suggestion,
    stores it as ``pending_approval``, and returns it.  Human approval remains
    mandatory before any execution.
    """
    case_store = get_case_store()
    case = _case_or_404(case_id)

    if case["status"] != "needs_follow_up":
        raise HTTPException(
            status_code=409,
            detail=(
                f"case in status {case['status']!r} cannot prepare a follow-up "
                "action; must be needs_follow_up"
            ),
        )

    followup_store = get_followup_store()
    max_followups = get_max_followups()
    followup_count = followup_store.get_followup_count(case_id)
    if followup_count > max_followups:
        raise HTTPException(
            status_code=409,
            detail=(
                f"maximum follow-up attempts ({max_followups}) reached for "
                "this case; human intervention required"
            ),
        )

    try:
        proposal: PreparedActionResult = prepare_followup_action(
            case_store,
            get_response_store(),
            get_action_store(),
            followup_store,
            case_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"follow-up preparation failed: {exc}",
        ) from exc
    except Exception as exc:
        logger.exception("unexpected follow-up preparer error")
        raise HTTPException(
            status_code=500,
            detail="follow-up preparation service error",
        ) from exc

    try:
        action = get_action_store().create_action(
            case_id,
            type=proposal.type,
            target=proposal.target,
            title=proposal.title,
            reason=proposal.reason,
            content=proposal.content,
        )
        action = get_action_store().submit_for_approval(action["id"])
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"invalid action data: {exc}") from exc

    return {
        "action": action,
        "followup": {
            "count": followup_count,
            "max_followups": max_followups,
        },
        "note": "This follow-up action awaits human approval and will not be "
        "sent or executed until approved.",
    }