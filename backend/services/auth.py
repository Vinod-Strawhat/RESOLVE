"""Opaque session-token and cookie helpers (Phase 8A).

The raw token is generated cryptographically and exists only long enough
to be set as the ``resolve_session`` cookie on the login/signup response.
Only ``sha256(token)`` is ever persisted (see
:mod:`backend.services.session_store`).
"""

import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone

from starlette.responses import Response

COOKIE_NAME = "resolve_session"

DEFAULT_SESSION_DAYS = 30
MIN_SESSION_TOKEN_BYTES = 32


def _now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_email(email: str) -> str:
    """Normalize an email for storage/lookup: lowercase + strip."""
    return email.strip().lower()


def get_session_ttl() -> timedelta:
    """Session lifetime from ``AUTH_SESSION_DAYS`` (default 30 days)."""
    raw = os.environ.get("AUTH_SESSION_DAYS")
    if raw is not None:
        try:
            days = float(raw)
            if 0 <= days:
                return timedelta(days=days)
        except (TypeError, ValueError):
            pass
    return timedelta(days=DEFAULT_SESSION_DAYS)


def get_session_expiry() -> str:
    """ISO-8601 UTC expiry for a new session."""
    return (_now() + get_session_ttl()).isoformat()


def get_cookie_secure() -> bool:
    """Whether the auth cookie carries ``Secure`` (prod HTTPS) or not (local HTTP)."""
    raw = os.environ.get("AUTH_COOKIE_SECURE", "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def generate_session_token() -> str:
    """Return an opaque token from >= 32 cryptographically secure bytes."""
    return secrets.token_urlsafe(MIN_SESSION_TOKEN_BYTES)


def hash_token(token: str) -> str:
    """Return the SHA-256 hex digest stored for ``token``."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=int(get_session_ttl().total_seconds()),
        path="/",
        httponly=True,
        samesite="strict",
        secure=get_cookie_secure(),
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=COOKIE_NAME,
        path="/",
        httponly=True,
        samesite="strict",
        secure=get_cookie_secure(),
    )