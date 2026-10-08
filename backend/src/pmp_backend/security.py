"""Password hashing (Argon2) and login tokens (JWT), per docs/coding-standards.md."""

import secrets
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError

_hasher = PasswordHasher()
_ALGORITHM = "HS256"


# No characters that look alike (0/O, 1/l/I), so a printed password reads well.
_READABLE = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789"


def generate_temporary_password() -> str:
    """12 random readable characters in groups of 4, e.g. "k7Qm-x9Ta-PwE3"."""
    characters = "".join(secrets.choice(_READABLE) for _ in range(12))
    return "-".join(characters[start : start + 4] for start in range(0, 12, 4))


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerificationError:
        return False


def issue_token(user_id: int, role: str, secret: str, lifetime: timedelta) -> str:
    now = datetime.now(UTC)
    # The Role is informational for clients; the backend always reads the current
    # Role from the database.
    claims = {"sub": str(user_id), "role": role, "iat": now, "exp": now + lifetime}
    return jwt.encode(claims, secret, algorithm=_ALGORITHM)


def read_token(token: str, secret: str) -> int | None:
    """The user id in a valid, unexpired token; None otherwise."""
    try:
        claims = jwt.decode(token, secret, algorithms=[_ALGORITHM])
        return int(claims["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None
