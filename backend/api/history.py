"""Case history retrieval (Phase 7C).

Exposes the combined resolution timeline for a case, assembled by
:mod:`backend.services.case_history` from the existing persisted stores.
"""

from fastapi import APIRouter, HTTPException

from backend.services.action_store import get_action_store
from backend.services.case_history import build_case_history
from backend.services.case_store import get_case_store
from backend.services.evaluation_store import get_evaluation_store
from backend.services.followup_store import get_followup_store
from backend.services.response_store import get_response_store

router = APIRouter(prefix="/api/cases", tags=["case-history"])


@router.get("/{case_id}/history")
def get_case_history(case_id: str) -> dict:
    case = get_case_store().get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="case not found")
    events = build_case_history(
        case,
        response_store=get_response_store(),
        evaluation_store=get_evaluation_store(),
        action_store=get_action_store(),
        followup_store=get_followup_store(),
    )
    return {"case_id": case_id, "case": case, "events": events}