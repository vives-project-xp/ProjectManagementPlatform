"""Managing Users: the Superuser's work (spec #3, user service)."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from pmp_backend.domain import Programme, Role, Year
from pmp_backend.models import User
from pmp_backend.security import hash_password


class UserError(Exception):
    """A User could not be created as asked; the message is fit to show."""


class DuplicateEmailError(UserError):
    pass


def normalize_email(email: str) -> str:
    return email.strip().lower()


def find_by_email(session: Session, email: str) -> User | None:
    """The User with this email, compared case-insensitively."""
    return session.scalar(select(User).where(User.email == normalize_email(email)))


def list_users(session: Session) -> list[User]:
    return list(session.scalars(select(User).order_by(User.last_name, User.first_name)))


def create_user(
    session: Session,
    *,
    role: Role,
    first_name: str,
    last_name: str,
    email: str,
    temporary_password: str,
    programme: Programme | None = None,
    year: Year | None = None,
) -> User:
    """A new User who must replace `temporary_password` at their first login."""
    if role is Role.SUPERUSER:
        raise UserError("Only Teachers and Students can be created.")
    is_student = role is Role.STUDENT
    if is_student and (programme is None or year is None):
        raise UserError("A Student needs a Programme and a Year.")
    if not is_student and (programme is not None or year is not None):
        raise UserError("Only Students have a Programme and a Year.")
    email = normalize_email(email)
    if find_by_email(session, email) is not None:
        raise DuplicateEmailError(f"The email address {email} is already in use.")

    user = User(
        first_name=first_name,
        last_name=last_name,
        email=email,
        password_hash=hash_password(temporary_password),
        role=role.value,
        must_change_password=True,
        programme=programme.value if programme else None,
        year=year.value if year else None,
    )
    session.add(user)
    session.commit()
    return user
