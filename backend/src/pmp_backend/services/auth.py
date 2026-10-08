"""Logging in and changing passwords."""

import time
from collections.abc import Callable

from sqlalchemy.orm import Session

from pmp_backend.models import User
from pmp_backend.security import hash_password, verify_password
from pmp_backend.services.users import find_by_email, normalize_email

MIN_PASSWORD_LENGTH = 8
MAX_FAILURES = 5
LOCK_SECONDS = 15 * 60


class PasswordChangeError(Exception):
    pass


class LoginGuard:
    """Locks an email for 15 minutes after 5 wrong passwords within 15 minutes,
    so passwords cannot be guessed. Kept in memory (one backend process): a
    restart forgets it."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._failures: dict[str, list[float]] = {}

    def _recent(self, email: str) -> list[float]:
        since = self._clock() - LOCK_SECONDS
        recent = [at for at in self._failures.get(email, []) if at > since]
        if recent:
            self._failures[email] = recent
        else:
            self._failures.pop(email, None)
        return recent

    def is_locked(self, email: str) -> bool:
        return len(self._recent(normalize_email(email))) >= MAX_FAILURES

    def failed(self, email: str) -> None:
        email = normalize_email(email)
        self._failures[email] = [*self._recent(email), self._clock()]

    def succeeded(self, email: str) -> None:
        self._failures.pop(normalize_email(email), None)


def authenticate(session: Session, email: str, password: str) -> User | None:
    """The active User with these credentials, or None (never says what failed)."""
    user = find_by_email(session, email)
    if user is None or not user.is_active:
        return None
    if not verify_password(user.password_hash, password):
        return None
    return user


def change_password(
    session: Session, user: User, current_password: str, new_password: str
) -> None:
    if not verify_password(user.password_hash, current_password):
        raise PasswordChangeError("Your current password is incorrect.")
    if len(new_password) < MIN_PASSWORD_LENGTH:
        raise PasswordChangeError(
            f"Your new password must be at least {MIN_PASSWORD_LENGTH} characters."
        )
    user.password_hash = hash_password(new_password)
    user.must_change_password = False
    session.commit()
