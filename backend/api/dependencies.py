"""Reusable authentication and ownership dependencies (Phase 8A/8B).

``get_current_user`` resolves the ``resolve_session`` cookie to an
authenticated user.  ``get_case_or_404_for_user`` / ``get_action_or_404_for_user``
enforce per-user case/action ownership and return ``404`` (never ``403``)
so foreign resources are indistinguishable from missing ones.

``require_same_origin`` guards state-changing cookie-authenticated routes
against cross-origin CSRF requests.
"""

import os
from datetime import datetime, timezone
from urllib.parse import urlparse

from fastapi import Cookie, HTTPException, Request

from backend.services.action_store import get_action_store
from backend.services.auth import COOKIE_NAME, hash_token
from backend.services.case_store import get_case_store
from backend.services.session_store import get_session_store
from backend.services.user_store import get_user_store

_UNAUTHENTICATED = HTTPException(status_code=401, detail="not authenticated")


def get_current_user(resolve_session: str | None = Cookie(default=None)) -> dict:
    """Validate the ``resolve_session`` cookie and return the user record.

    Rejects missing, unknown, or expired sessions with a uniform 401.
    """
    if not resolve_session:
        raise _UNAUTHENTICATED

    token_hash = hash_token(resolve_session)
    session_store = get_session_store()
    session = session_store.get_session(token_hash)
    if session is None:
        raise _UNAUTHENTICATED

    now = datetime.now(timezone.utc).isoformat()
    if session["expires_at"] <= now:
        session_store.delete_session(token_hash)
        raise _UNAUTHENTICATED

    user = get_user_store().get_user(session["user_id"])
    if user is None:
        raise _UNAUTHENTICATED

    return user


def get_case_or_404_for_user(case_id: str, user_id: str) -> dict:
    """Return a case owned by ``user_id`` or raise a uniform 404.

    Missing and foreign cases are indistinguishable (always 404) to avoid
    leaking resource existence to other users.
    """
    case = get_case_store().get_case(case_id)
    if case is None or case.get("user_id") != user_id:
        raise HTTPException(status_code=404, detail="case not found")
    return case


def get_action_or_404_for_user(action_id: str, user_id: str) -> dict:
    """Return an action owned by ``user_id`` or raise a uniform 404.

    Ownership is derived from the action's owning case; missing and foreign
    actions are indistinguishable (always 404).
    """
    action = get_action_store().get_action(action_id)
    if action is None:
        raise HTTPException(status_code=404, detail="action not found")
    case = get_case_store().get_case(action.get("case_id") or "")
    if case is None or case.get("user_id") != user_id:
        raise HTTPException(status_code=404, detail="action not found")
    return action


def _allowed_cors_origins() -> set[str]:
    raw = os.getenv("CORS_ORIGINS", "http://localhost:5174")
    return {origin.strip() for origin in raw.split(",") if origin.strip()}


def _origin_from_referer(referer: str) -> str | None:
    parsed = urlparse(referer)
    if not parsed.scheme or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


def is_same_origin(request: Request) -> bool:
    """Whether the request's Origin (or Referer fallback) is allowed.

    Requests with neither header (e.g. CLI tools) are treated as safe.

    When a dev proxy rewrites ``Origin`` to the API host, the browser
    ``Referer`` still reflects the frontend URL and is checked as a fallback.
    """
    allowed = _allowed_cors_origins()

    origin = request.headers.get("origin")
    if origin and origin in allowed:
        return True

    referer = request.headers.get("referer")
    if referer:
        referer_origin = _origin_from_referer(referer)
        if referer_origin and referer_origin in allowed:
            return True

    if not origin and not referer:
        return True
    return False


async def require_same_origin(request: Request) -> None:
    """Reject cross-origin state-changing requests (CSRF guard).

    Wire into cookie-authenticated mutation routes (POST/PUT/PATCH/DELETE);
    GET routes are intentionally exempt.
    """
    if not is_same_origin(request):
        raise HTTPException(status_code=403, detail="cross-origin request rejected")
