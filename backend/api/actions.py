import logging

from fastapi import APIRouter, HTTPException

from backend.services.action_store import get_action_store
from backend.services.case_store import get_case_store

logger = logging.getLogger(__name__)

router = APIRouter(tags=["actions"])


def _get_action_or_404(action_id: str) -> dict:
    action = get_action_store().get_action(action_id)
    if action is None:
        raise HTTPException(status_code=404, detail="action not found")
    return action


@router.get("/api/cases/{case_id}/actions")
def list_case_actions(case_id: str) -> dict:
    if get_case_store().get_case(case_id) is None:
        raise HTTPException(status_code=404, detail="case not found")
    actions = get_action_store().list_actions_for_case(case_id)
    return {"case_id": case_id, "actions": actions}


@router.get("/api/actions/{action_id}")
def get_action(action_id: str) -> dict:
    return {"action": _get_action_or_404(action_id)}


@router.post("/api/actions/{action_id}/approve")
def approve_action(action_id: str) -> dict:
    _get_action_or_404(action_id)
    try:
        action = get_action_store().approve_action(action_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"action": action}


@router.post("/api/actions/{action_id}/reject")
def reject_action(action_id: str) -> dict:
    _get_action_or_404(action_id)
    try:
        action = get_action_store().reject_action(action_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"action": action}