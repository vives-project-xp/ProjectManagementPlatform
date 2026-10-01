"""Password hashing (Argon2) and login tokens (JWT), per docs/coding-standards.md."""

from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError

_hasher = PasswordHasher()
_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerificationError:
        return False


def issue_token(user_id: int, secret: str, lifetime: timedelta) -> str:
    now = datetime.now(UTC)
    claims = {"sub": str(user_id), "iat": now, "exp": now + lifetime}
    return jwt.encode(claims, secret, algorithm=_ALGORITHM)


def read_token(token: str, secret: str) -> int | None:
    """The user id in a valid, unexpired token; None otherwise."""
    try:
        claims = jwt.decode(token, secret, algorithms=[_ALGORITHM])
        return int(claims["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None
