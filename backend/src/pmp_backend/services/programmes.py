"""The Programme list, managed by the Superuser (spec #24, ADR 0004).

Users keep their Programme as text; this list decides which names are valid.
Renaming a Programme renames it for every User, but never in the Makers, which
record the Programme as it was when the Project was archived.
"""

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from pmp_backend.errors import Conflict, NotFound, Refused
from pmp_backend.models import Programme, User


class ProgrammeError(Refused):
    """A Programme could not be used or changed as asked; the message is fit to show."""


class ProgrammeNotFoundError(ProgrammeError, NotFound):
    pass


class ProgrammeConflictError(ProgrammeError, Conflict):
    pass


def list_programmes(session: Session) -> list[Programme]:
    return list(session.scalars(select(Programme).order_by(func.lower(Programme.name))))


def _find(session: Session, name: str, *, lock: bool = False) -> Programme | None:
    """The Programme with this name, ignoring case and surrounding spaces."""
    query = select(Programme).where(func.lower(Programme.name) == name.strip().lower())
    if lock:
        # Shared lock: a rename or removal of this Programme waits until the
        # User who is being saved with it is committed (and vice versa).
        query = query.with_for_update(read=True)
    return session.scalar(query)


def existing_name(session: Session, name: str, *, lock: bool = False) -> str:
    """The Programme's name as it is spelled in the list; refused when unknown."""
    programme = _find(session, name, lock=lock)
    if programme is None:
        raise ProgrammeError(f"{name.strip()} is not a Programme in the list.")
    return programme.name


def first_programme_name(session: Session) -> str | None:
    """The oldest Programme in the list, if there is any."""
    return session.scalar(select(Programme.name).order_by(Programme.id).limit(1))


def _get(session: Session, programme_id: int) -> Programme:
    programme = session.scalar(
        select(Programme).where(Programme.id == programme_id).with_for_update()
    )
    if programme is None:
        raise ProgrammeNotFoundError("This Programme does not exist.")
    return programme


def _check_name_free(session: Session, name: str, programme_id: int | None) -> None:
    other = _find(session, name)
    if other is not None and other.id != programme_id:
        raise ProgrammeConflictError(f"The Programme {other.name} already exists.")


def _commit(session: Session, name: str) -> None:
    try:
        session.commit()
    except IntegrityError as error:
        # Someone else saved the same name between the check and the save.
        session.rollback()
        raise ProgrammeConflictError(f"The Programme {name} already exists.") from error


def add_programme(session: Session, name: str) -> Programme:
    name = name.strip()
    _check_name_free(session, name, None)
    programme = Programme(name=name)
    session.add(programme)
    _commit(session, name)
    return programme


def rename_programme(session: Session, programme_id: int, name: str) -> Programme:
    """Rename a Programme, for every User who has it, in one transaction."""
    name = name.strip()
    programme = _get(session, programme_id)
    _check_name_free(session, name, programme.id)
    session.execute(
        update(User).where(User.programme == programme.name).values(programme=name)
    )
    programme.name = name
    _commit(session, name)
    return programme


def remove_programme(session: Session, programme_id: int) -> None:
    """Remove a Programme from the list; refused while any User has it."""
    programme = _get(session, programme_id)
    holders = session.scalar(
        select(func.count()).select_from(User).where(User.programme == programme.name)
    )
    if holders:
        who = "1 User still has" if holders == 1 else f"{holders} Users still have"
        raise ProgrammeConflictError(
            f"{who} the Programme {programme.name}. Change their Programme first."
        )
    session.delete(programme)
    session.commit()
