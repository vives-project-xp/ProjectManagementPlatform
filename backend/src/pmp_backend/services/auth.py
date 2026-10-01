"""Logging in and changing passwords."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from pmp_backend.models import User
from pmp_backend.security import hash_password, verify_password

MIN_PASSWORD_LENGTH = 8


class PasswordChangeError(Exception):
    pass


def normalize_email(email: str) -> str:
    return email.strip().lower()


def authenticate(session: Session, email: str, password: str) -> User | None:
    """The active User with these credentials, or None (never says what failed)."""
    user = session.scalar(select(User).where(User.email == normalize_email(email)))
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
