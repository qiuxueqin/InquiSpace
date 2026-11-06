"""Password and opaque-token primitives used by authentication services."""

import hashlib
import hmac
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

_password_hasher = PasswordHasher()  # Library's Argon2id defaults; random salt per password.


def hash_password(password: str) -> str:
    if not password or password.isspace():
        raise ValueError("Password must not be blank")
    return _password_hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _password_hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def generate_token() -> str:
    """Return a high-entropy URL-safe secret for a session or CSRF token."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Hash an opaque token before persistence; the token itself is never stored."""
    return hashlib.sha256(token.encode("utf-8"), usedforsecurity=True).hexdigest()


def tokens_equal(left: str, right: str) -> bool:
    """Compare token strings without leaking equality through timing."""
    return hmac.compare_digest(left, right)
