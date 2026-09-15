"""Phase 8B legacy-ownership backfill.

Pre-Phase 8B databases contain ``cases`` and ``sessions`` rows created
before the ``user_id`` column existed.  This module deterministically
attributes every unowned row to a single dedicated local account
(``legacy@local.resolve``) whose password is randomly generated and never
exposed.  It is designed to be idempotent and safe to run on every
startup.
"""

import secrets

from backend.services.auth import normalize_email
from backend.services.case_store import CaseStore
from backend.services.memory_store import MemoryStore
from backend.services.passwords import hash_password
from backend.services.user_store import UserStore

LEGACY_EMAIL = "legacy@local.resolve"

LEGACY_DISPLAY_NAME = "Legacy Local Owner"


def _random_password() -> str:
    """Return a high-entropy password used once and then discarded."""
    return secrets.token_urlsafe(48)


def _get_or_create_legacy_user(user_store: UserStore) -> dict:
    """Return the legacy owner, creating it on first run."""
    existing = user_store.get_user_by_email(LEGACY_EMAIL)
    if existing is not None:
        return existing
    return user_store.create_user(
        email=LEGACY_EMAIL,
        password_hash=hash_password(_random_password()),
        display_name=LEGACY_DISPLAY_NAME,
    )


def migrate_legacy_ownership(
    *,
    case_store: CaseStore,
    memory_store: MemoryStore,
    user_store: UserStore,
) -> dict:
    """Backfill unowned cases and sessions to the legacy owner.

    Idempotent: rows already attributed are never touched.  Returns a
    summary dict of claimed counts for observability.
    """
    legacy_user = _get_or_create_legacy_user(user_store)
    cases_claimed = case_store.claim_unowned_cases(legacy_user["id"])
    sessions_claimed = memory_store.claim_unowned_sessions(legacy_user["id"])
    return {
        "owner_user_id": legacy_user["id"],
        "owner_email": LEGACY_EMAIL,
        "cases_claimed": cases_claimed,
        "sessions_claimed": sessions_claimed,
    }


def migrate_legacy_ownership_default() -> dict:
    """Run the migration against the live singleton stores.

    Intended for the FastAPI startup lifespan.
    """
    from backend.services.case_store import get_case_store
    from backend.services.memory_store import get_memory_store
    from backend.services.user_store import get_user_store

    return migrate_legacy_ownership(
        case_store=get_case_store(),
        memory_store=get_memory_store(),
        user_store=get_user_store(),
    )