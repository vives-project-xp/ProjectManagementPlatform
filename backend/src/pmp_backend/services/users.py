"""Managing Users: the Superuser's work (spec #3, user service)."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
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


def new_user(
    *,
    role: Role,
    first_name: str,
    last_name: str,
    email: str,
    temporary_password: str,
    programme: Programme | None = None,
    year: Year | None = None,
) -> User:
    """An unsaved User who must replace `temporary_password` at their first login."""
    is_student = role is Role.STUDENT
    if is_student and (programme is None or year is None):
        raise UserError("A Student needs a Programme and a Year.")
    if not is_student and (programme is not None or year is not None):
        raise UserError("Only Students have a Programme and a Year.")
    return User(
        first_name=first_name,
        last_name=last_name,
        email=normalize_email(email),
        password_hash=hash_password(temporary_password),
        role=role.value,
        must_change_password=True,
        programme=programme.value if programme else None,
        year=year.value if year else None,
    )


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
    """Create a Teacher or Student (the Superuser exists only as a starting account)."""
    if role is Role.SUPERUSER:
        raise UserError("Only Teachers and Students can be created.")
    user = new_user(
        role=role,
        first_name=first_name,
        last_name=last_name,
        email=email,
        temporary_password=temporary_password,
        programme=programme,
        year=year,
    )
    duplicate = DuplicateEmailError(
        f"The email address {user.email} is already in use."
    )
    if find_by_email(session, user.email) is not None:
        raise duplicate
    session.add(user)
    try:
        session.commit()
    except IntegrityError as error:
        # Someone else took the email between the check and the insert.
        session.rollback()
        raise duplicate from error
    return user
