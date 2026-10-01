"""Managing Users: the Superuser's work (spec #3, user service)."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from pmp_backend.domain import Programme, Role, Year
from pmp_backend.errors import Conflict, NotFound, Refused
from pmp_backend.models import User
from pmp_backend.security import hash_password
from pmp_backend.services.projects import active_titles_owned_by


class UserError(Refused):
    """A User could not be saved as asked; the message is fit to show."""


class DuplicateEmailError(UserError, Conflict):
    pass


class UserNotFoundError(UserError, NotFound):
    pass


class UserConflictError(UserError, Conflict):
    pass


def normalize_email(email: str) -> str:
    return email.strip().lower()


def find_by_email(session: Session, email: str) -> User | None:
    """The User with this email, compared case-insensitively."""
    return session.scalar(select(User).where(User.email == normalize_email(email)))


def role_exists(session: Session, role: Role) -> bool:
    """Whether at least one User (active or not) has this Role."""
    return (
        session.scalar(select(User.id).where(User.role == role.value).limit(1))
        is not None
    )


def list_users(
    session: Session, *, role: Role | None = None, active: bool | None = None
) -> list[User]:
    query = select(User).order_by(User.last_name, User.first_name)
    if role is not None:
        query = query.where(User.role == role.value)
    if active is not None:
        query = query.where(User.is_active == active)
    return list(session.scalars(query))


def list_students(session: Session) -> list[User]:
    """Every Student, active or not, with the Project they are a Member of."""
    return list_users(session, role=Role.STUDENT)


def get_user(session: Session, user_id: int) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise UserNotFoundError("This User does not exist.")
    return user


def _check_student_fields(
    role: Role, programme: Programme | None, year: Year | None
) -> None:
    is_student = role is Role.STUDENT
    if is_student and (programme is None or year is None):
        raise UserError("A Student needs a Programme and a Year.")
    if not is_student and (programme is not None or year is not None):
        raise UserError("Only Students have a Programme and a Year.")


def _check_email_free(session: Session, email: str, user_id: int | None) -> None:
    owner = find_by_email(session, email)
    if owner is not None and owner.id != user_id:
        raise DuplicateEmailError(f"The email address {email} is already in use.")


def _commit(session: Session, email: str) -> None:
    try:
        session.commit()
    except IntegrityError as error:
        # Someone else took the email between the check and the save.
        session.rollback()
        raise DuplicateEmailError(
            f"The email address {email} is already in use."
        ) from error


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
    _check_student_fields(role, programme, year)
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
    _check_email_free(session, user.email, None)
    session.add(user)
    _commit(session, user.email)
    return user


def update_user(
    session: Session,
    user_id: int,
    *,
    first_name: str,
    last_name: str,
    email: str,
    programme: Programme | None = None,
    year: Year | None = None,
) -> User:
    """Correct a User's details; the Role never changes after creation."""
    user = get_user(session, user_id)
    _check_student_fields(Role(user.role), programme, year)
    email = normalize_email(email)
    _check_email_free(session, email, user.id)
    user.first_name = first_name
    user.last_name = last_name
    user.email = email
    user.programme = programme.value if programme else None
    user.year = year.value if year else None
    _commit(session, email)
    return user


def deactivate_user(session: Session, user_id: int, acting_user: User) -> User:
    """Stop a User from logging in; they and their links to Projects are kept."""
    user = get_user(session, user_id)
    if user.id == acting_user.id:
        raise UserConflictError("You cannot deactivate yourself.")
    owned = active_titles_owned_by(session, user.id)
    if owned:
        raise UserConflictError(
            f"{user.full_name} is the Product Owner of these "
            f"active Projects: {', '.join(owned)}. Choose another Product Owner "
            "first."
        )
    user.is_active = False
    session.commit()
    return user


def reactivate_user(session: Session, user_id: int) -> User:
    user = get_user(session, user_id)
    user.is_active = True
    session.commit()
    return user


def reset_password(session: Session, user_id: int, temporary_password: str) -> None:
    """Give a User a new Temporary password, to be replaced at their next login."""
    user = get_user(session, user_id)
    user.password_hash = hash_password(temporary_password)
    user.must_change_password = True
    session.commit()
