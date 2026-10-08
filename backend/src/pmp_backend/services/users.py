"""Managing Users: the Superuser's work (spec #3, user service)."""

import csv
import re
from dataclasses import dataclass

from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from pmp_backend.domain import Role, Year
from pmp_backend.errors import Conflict, NotFound, Refused
from pmp_backend.models import User
from pmp_backend.security import generate_temporary_password, hash_password
from pmp_backend.services import github, programmes
from pmp_backend.services.projects import (
    active_titles_owned_by,
    titles_made_by,
    titles_owned_by,
)


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


def any_users(session: Session) -> bool:
    """Whether at least one User (active or not) exists."""
    return session.scalar(select(User.id).limit(1)) is not None


def _users_query(*, role: Role | None = None, active: bool | None = None) -> Select:
    """Users sorted by name, optionally of one Role and/or active state."""
    query = select(User).order_by(User.last_name, User.first_name)
    if role is not None:
        query = query.where(User.role == role.value)
    if active is not None:
        query = query.where(User.is_active == active)
    return query


def list_users(
    session: Session, *, role: Role | None = None, active: bool | None = None
) -> list[User]:
    return list(session.scalars(_users_query(role=role, active=active)))


def list_students(
    session: Session,
    *,
    without_project: bool = False,
    programme: str | None = None,
    year: Year | None = None,
) -> list[User]:
    """Students, active or not, with the Project they are a Member of; optionally
    only those without a Project yet, or of one Programme and/or Year."""
    query = _users_query(role=Role.STUDENT)
    if without_project:
        query = query.where(User.project_id.is_(None))
    if programme is not None:
        query = query.where(
            User.programme == programmes.existing_name(session, programme)
        )
    if year is not None:
        query = query.where(User.year == year.value)
    return list(session.scalars(query))


def get_user(session: Session, user_id: int) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise UserNotFoundError("This User does not exist.")
    return user


def _check_student_fields(role: Role, programme: str | None, year: Year | None) -> None:
    is_student = role is Role.STUDENT
    if is_student and (programme is None or year is None):
        raise UserError("A Student needs a Programme and a Year.")
    if not is_student and (programme is not None or year is not None):
        raise UserError("Only Students have a Programme and a Year.")


def _student_programme(
    session: Session, role: Role, programme: str | None, year: Year | None
) -> str | None:
    """Check the Student-only fields; the Programme as it is spelled in the list."""
    _check_student_fields(role, programme, year)
    if programme is None:
        return None
    return programmes.existing_name(session, programme, lock=True)


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
    programme: str | None = None,
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
        programme=programme,
        year=year.value if year else None,
    )


def _check_creatable(role: Role) -> None:
    if role is Role.SUPERUSER:
        raise UserError("Only Teachers and Students can be created.")


def create_user(
    session: Session,
    *,
    role: Role,
    first_name: str,
    last_name: str,
    email: str,
    programme: str | None = None,
    year: Year | None = None,
) -> tuple[User, str]:
    """Create a Teacher or Student (the Superuser exists only as a starting
    account), with a generated Temporary password; the User and that password."""
    _check_creatable(role)
    programme = _student_programme(session, role, programme, year)
    password = generate_temporary_password()
    user = new_user(
        role=role,
        first_name=first_name,
        last_name=last_name,
        email=email,
        temporary_password=password,
        programme=programme,
        year=year,
    )
    _check_email_free(session, user.email, None)
    session.add(user)
    _commit(session, user.email)
    return user, password


def update_user(
    session: Session,
    user_id: int,
    *,
    first_name: str,
    last_name: str,
    email: str,
    programme: str | None = None,
    year: Year | None = None,
) -> User:
    """Correct a User's details; the Role never changes after creation."""
    user = get_user(session, user_id)
    programme = _student_programme(session, Role(user.role), programme, year)
    email = normalize_email(email)
    _check_email_free(session, email, user.id)
    user.first_name = first_name
    user.last_name = last_name
    user.email = email
    user.programme = programme
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


def _why_not_deletable(session: Session, user: User) -> str | None:
    """Why this User is linked to a Project, or None when they are not."""
    if user.project is not None:
        return f"is a Member of {user.project.title}"
    made = titles_made_by(session, user.id)
    if made:
        return f"is in the Makers of {', '.join(made)}"
    owned = titles_owned_by(session, user.id)
    if owned:
        return f"is the Product Owner of {', '.join(owned)}"
    return None


def delete_user(session: Session, user_id: int) -> None:
    """Remove a Student or Teacher who is not linked to any Project; their email
    becomes free and their token stops working on its next request."""
    # Locked like adding a Member or archiving (both lock the Student's row), so
    # the User cannot become linked between the checks and the delete.
    user = session.get(User, user_id, with_for_update={"of": User})
    if user is None:
        raise UserNotFoundError("This User does not exist.")
    if user.role == Role.SUPERUSER.value:
        raise UserConflictError("The Superuser cannot be deleted.")
    reason = _why_not_deletable(session, user)
    if reason is not None:
        raise UserConflictError(
            f"{user.full_name} {reason}, so they cannot be deleted. "
            "Deactivate them instead."
        )
    name = user.full_name
    session.delete(user)
    try:
        session.commit()
    except IntegrityError as error:
        # A Project got this Teacher as Product Owner after the check.
        session.rollback()
        raise UserConflictError(
            f"{name} was just made a Product Owner, so they cannot be deleted. "
            "Deactivate them instead."
        ) from error


def reset_password(session: Session, user_id: int) -> str:
    """Give a User a new, generated Temporary password, to be replaced at their
    next login; that password (shown once, only its hash is kept)."""
    user = get_user(session, user_id)
    password = generate_temporary_password()
    user.password_hash = hash_password(password)
    user.must_change_password = True
    session.commit()
    return password


def set_github_username(
    session: Session, client: github.GitHub, user_id: int, username: str | None
) -> User:
    """Save (as GitHub spells it) or clear a User's GitHub username; refused when
    GitHub has no such account or another User already has it."""
    user = get_user(session, user_id)
    if not username:
        user.github_username = None
        session.commit()
        return user
    login = github.find_account(client, username).login
    taken = f"The GitHub username {login} is already used by another User."
    owner = session.scalar(
        select(User).where(func.lower(User.github_username) == login.lower())
    )
    if owner is not None and owner.id != user.id:
        raise UserConflictError(taken)
    user.github_username = login
    try:
        session.commit()
    except IntegrityError as error:
        # Someone else saved it between the check and the save.
        session.rollback()
        raise UserConflictError(taken) from error
    return user


# Importing Users from a CSV file

MAX_IMPORT_LINES = 1000
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass(frozen=True)
class ImportedUser:
    user: User
    temporary_password: str


@dataclass(frozen=True)
class SkippedLine:
    line: int
    email: str | None
    reason: str


def _csv_rows(content: bytes) -> list[list[str]]:
    """The file's lines as cells; UTF-8 with or without BOM, "," or ";"."""
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise UserError("The file must be a UTF-8 CSV file.") from error
    lines = text.splitlines()
    if len(lines) > MAX_IMPORT_LINES:
        raise UserError(f"The file has more than {MAX_IMPORT_LINES} lines.")
    # Belgian Excel separates with ";".
    first = lines[0] if lines else ""
    delimiter = ";" if first.count(";") > first.count(",") else ","
    return [
        [cell.strip() for cell in row] for row in csv.reader(lines, delimiter=delimiter)
    ]


def _skip_reason(session: Session, cells: list[str], seen: set[str]) -> str | None:
    if len(cells) != 3:
        return "A line needs 3 values: Firstname,Lastname,email."
    first_name, last_name, email = cells
    if not first_name or not last_name:
        return "A first and a last name are needed."
    if len(first_name) > 100 or len(last_name) > 100:
        return "A name can be at most 100 characters."
    if not EMAIL.match(email) or len(email) > 254:
        return f"{email} is not a valid email address."
    email = normalize_email(email)
    if email in seen:
        return f"{email} appears more than once in the file."
    if find_by_email(session, email) is not None:
        return f"The email address {email} is already in use."
    return None


def import_users(
    session: Session,
    content: bytes,
    *,
    role: Role,
    programme: str | None = None,
    year: Year | None = None,
) -> tuple[list[ImportedUser], list[SkippedLine]]:
    """Create a User for every valid `Firstname,Lastname,email` line, each with
    its own generated Temporary password; the other lines are skipped with the
    reason. Role, Programme and Year are the same for the whole file."""
    _check_creatable(role)
    programme = _student_programme(session, role, programme, year)
    created: list[ImportedUser] = []
    skipped: list[SkippedLine] = []
    seen: set[str] = set()
    for number, cells in enumerate(_csv_rows(content), start=1):
        if not any(cells):
            continue
        # A first line without an email is the header (any language).
        if number == 1 and len(cells) == 3 and "@" not in cells[2]:
            continue
        reason = _skip_reason(session, cells, seen)
        if reason is not None:
            email = normalize_email(cells[2]) if len(cells) == 3 else None
            skipped.append(SkippedLine(line=number, email=email, reason=reason))
            continue
        first_name, last_name, email = cells
        password = generate_temporary_password()
        user = new_user(
            role=role,
            first_name=first_name,
            last_name=last_name,
            email=email,
            temporary_password=password,
            programme=programme,
            year=year,
        )
        seen.add(user.email)
        session.add(user)
        created.append(ImportedUser(user=user, temporary_password=password))
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise DuplicateEmailError(
            "Someone created one of these Users at the same moment. "
            "Import the file again."
        ) from error
    return created, skipped
