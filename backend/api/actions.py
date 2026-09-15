import logging

from fastapi import APIRouter, Depends, HTTPException

from backend.api.dependencies import (
    get_action_or_404_for_user,
    get_case_or_404_for_user,
    get_current_user,
    require_same_origin,
)
from backend.services.action_executor import get_executor
from backend.services.action_store import get_action_store

logger = logging.getLogger(__name__)

router = APIRouter(tags=["actions"])


@router.get("/api/cases/{case_id}/actions")
def list_case_actions(
    case_id: str,
    user: dict = Depends(get_current_user),
) -> dict:
    get_case_or_404_for_user(case_id, user["id"])
    actions = get_action_store().list_actions_for_case(case_id)
    return {"case_id": case_id, "actions": actions}


@router.get("/api/actions/{action_id}")
def get_action(
    action_id: str,
    user: dict = Depends(get_current_user),
) -> dict:
    return {"action": get_action_or_404_for_user(action_id, user["id"])}


@router.post("/api/actions/{action_id}/approve")
def approve_action(
    action_id: str,
    user: dict = Depends(get_current_user),
    _same_origin: None = Depends(require_same_origin),
) -> dict:
    get_action_or_404_for_user(action_id, user["id"])
    try:
        action = get_action_store().approve_action(action_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"action": action}


@router.post("/api/actions/{action_id}/reject")
def reject_action(
    action_id: str,
    user: dict = Depends(get_current_user),
    _same_origin: None = Depends(require_same_origin),
) -> dict:
    get_action_or_404_for_user(action_id, user["id"])
    try:
        action = get_action_store().reject_action(action_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"action": action}


@router.post("/api/actions/{action_id}/execute")
def execute_action(
    action_id: str,
    user: dict = Depends(get_current_user),
    _same_origin: None = Depends(require_same_origin),
) -> dict:
    get_action_or_404_for_user(action_id, user["id"])
    try:
        get_executor().execute(action_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"action": get_action_store().get_action(action_id)}