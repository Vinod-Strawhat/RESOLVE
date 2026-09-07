import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.services.case_store import (
    EVALUATION_OUTCOMES,
    get_case_store,
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