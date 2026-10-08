"""The Top 3 (spec #37): which Projects Students may choose, and the one round
in which they choose."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from pmp_backend.errors import Conflict, Refused
from pmp_backend.models import Project, Top3Choice, Top3Round
from pmp_backend.services.projects import changeable_project


class Top3Error(Refused):
    """A Top 3 change was refused; the message is fit to show."""


class Top3ConflictError(Top3Error, Conflict):
    pass


@dataclass(frozen=True)
class RoundState:
    """The round's deadline (None before the first round) and whether it is open."""

    deadline: datetime | None
    is_open: bool


def set_open_for_choice(session: Session, project_id: int, value: bool) -> Project:
    """Whether Students may pick this Project; Archived Projects are refused."""
    project = changeable_project(session, project_id)
    project.open_for_choice = value
    session.commit()
    return project


def round_state(session: Session) -> RoundState:
    # Compared with the database's clock, like every other timestamp.
    row = session.execute(
        select(Top3Round.deadline, Top3Round.deadline > func.now())
    ).first()
    if row is None:
        return RoundState(deadline=None, is_open=False)
    return RoundState(deadline=row[0], is_open=row[1])


def _locked_round(session: Session) -> Top3Round | None:
    # Locked until commit, so two Teachers' changes cannot interleave.
    return session.scalar(select(Top3Round).with_for_update())


def _check_future(session: Session, deadline: datetime) -> None:
    if not session.scalar(select(func.now() < deadline)):
        raise Top3Error("The deadline must be in the future.")


def _save_deadline(session: Session, deadline: datetime) -> RoundState:
    current = _locked_round(session)
    if current is None:
        session.add(Top3Round(id=1, deadline=deadline))
    else:
        current.deadline = deadline
    session.commit()
    return round_state(session)


def set_deadline(session: Session, deadline: datetime) -> RoundState:
    """Open the round, reopen it or move its deadline; every Top 3 is kept."""
    _check_future(session, deadline)
    return _save_deadline(session, deadline)


def close_round(session: Session) -> RoundState:
    """Stop choosing now."""
    current = _locked_round(session)
    if current is None or not round_state(session).is_open:
        raise Top3ConflictError("The Top 3 round is not open.")
    current.deadline = func.now()
    session.commit()
    return round_state(session)


def start_new_round(session: Session, deadline: datetime) -> RoundState:
    """A new semester: clear every Top 3 and open the round, in one transaction."""
    _check_future(session, deadline)
    _locked_round(session)
    session.execute(delete(Top3Choice))
    return _save_deadline(session, deadline)
