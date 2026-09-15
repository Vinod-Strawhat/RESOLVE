"""Argon2 password hashing for user accounts (Phase 8A).

Plaintext passwords are never stored or logged.  Only the Argon2id hash
produced here is persisted in the ``users`` table.
"""

from argon2 import PasswordHasher
from argon2.exceptions import (
    InvalidHashError,
    VerificationError,
    VerifyMismatchError,
)

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    """Return an Argon2id hash for ``password``.

    The hash embeds a fresh random salt on every call, so identical
    passwords produce distinct hashes.
    """
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Return whether ``password`` matches ``password_hash``.

    Any failure (mismatch, malformed or unparsable stored hash) returns
    False; callers surface one generic authentication error either way.
    """
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError, VerificationError, ValueError):
        return False