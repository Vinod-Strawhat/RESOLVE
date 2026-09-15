"""Authentication endpoints (Phase 8A).

Provides signup/login/logout/me.  Sessions are opaque tokens delivered in
the HttpOnly ``resolve_session`` cookie; only their SHA-256 hashes are
persisted.  Never returns ``password_hash`` or a raw session token.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from backend.api.dependencies import get_current_user, require_same_origin
from backend.services.auth import (
    COOKIE_NAME,
    clear_session_cookie,
    generate_session_token,
    get_session_expiry,
    hash_token,
    normalize_email,
    set_session_cookie,
)
from backend.services.passwords import hash_password, verify_password
from backend.services.session_store import get_session_store
from backend.services.user_store import DuplicateEmailError, get_user_store

router = APIRouter(prefix="/api/auth", tags=["auth"])

MAX_EMAIL_LEN = 320
MAX_PASSWORD_LEN = 256
MAX_DISPLAY_NAME_LEN = 120

GENERIC_LOGIN_ERROR = "invalid email or password"


class SignupRequest(BaseModel):
    email: str = Field(min_length=1, max_length=MAX_EMAIL_LEN)
    password: str = Field(min_length=1, max_length=MAX_PASSWORD_LEN)
    display_name: str | None = Field(default=None, max_length=MAX_DISPLAY_NAME_LEN)


class LoginRequest(BaseModel):
    email: str = Field(min_length=1, max_length=MAX_EMAIL_LEN)
    password: str = Field(min_length=1, max_length=MAX_PASSWORD_LEN)


class UserPublic(BaseModel):
    id: str
    email: str
    display_name: str
    created_at: str


class AuthResponse(BaseModel):
    user: UserPublic


class MeResponse(BaseModel):
    user: UserPublic


class LogoutResponse(BaseModel):
    status: str


def _safe_user(user: dict) -> dict:
    return {
        "id": user["id"],
        "email": user["email"],
        "display_name": user["display_name"] or "",
        "created_at": user["created_at"],
    }


def _valid_email(email: str) -> bool:
    if not email or len(email) > MAX_EMAIL_LEN:
        return False
    if "@" not in email:
        return False
    return " " not in email and email.count("@") == 1


def _issue_session(response: Response, user_id: str) -> None:
    """Create a session for ``user_id`` and set the cookie on ``response``."""
    token = generate_session_token()
    get_session_store().create_session(
        user_id=user_id,
        token_hash=hash_token(token),
        expires_at=get_session_expiry(),
    )
    set_session_cookie(response, token)


@router.post("/signup", response_model=AuthResponse)
def signup(request: SignupRequest, response: Response) -> AuthResponse:
    email = normalize_email(request.email)
    password = request.password

    if not _valid_email(email):
        raise HTTPException(status_code=400, detail="invalid email address")
    if not password.strip():
        raise HTTPException(status_code=400, detail="password must not be empty")

    password_hash = hash_password(password)
    users = get_user_store()
    try:
        user = users.create_user(
            email=email,
            password_hash=password_hash,
            display_name=(request.display_name or "").strip() or None,
        )
    except DuplicateEmailError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    _issue_session(response, user["id"])
    return AuthResponse(user=UserPublic(**_safe_user(user)))


@router.post("/login", response_model=AuthResponse)
def login(request: LoginRequest, response: Response) -> AuthResponse:
    email = normalize_email(request.email)
    password = request.password

    if not email or not password.strip():
        raise HTTPException(status_code=401, detail=GENERIC_LOGIN_ERROR)

    user = get_user_store().get_user_by_email(email)
    if user is None or not verify_password(password, user["password_hash"]):
        raise HTTPException(status_code=401, detail=GENERIC_LOGIN_ERROR)

    _issue_session(response, user["id"])
    return AuthResponse(user=UserPublic(**_safe_user(user)))


@router.get("/me", response_model=MeResponse)
def me(user: dict = Depends(get_current_user)) -> MeResponse:
    return MeResponse(user=UserPublic(**_safe_user(user)))


@router.post("/logout", response_model=LogoutResponse)
def logout(
    request: Request,
    response: Response,
    _same_origin: None = Depends(require_same_origin),
) -> LogoutResponse:
    token = request.cookies.get(COOKIE_NAME)
    if token:
        get_session_store().delete_session(hash_token(token))
    clear_session_cookie(response)
    return LogoutResponse(status="logged_out")