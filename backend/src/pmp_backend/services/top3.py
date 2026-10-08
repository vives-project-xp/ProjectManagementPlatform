"""The Top 3 (spec #37): which Projects Students may choose, and the one round
in which they choose."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from pmp_backend.domain import ProjectStatus
from pmp_backend.errors import Conflict, Refused
from pmp_backend.models import Project, Top3Choice, Top3Round, User
from pmp_backend.services.projects import changeable_project

MAX_PLACES = 3


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


# A Student's Top 3


@dataclass(frozen=True)
class Choice:
    """One place of a submitted Top 3. `available` is false once its Project is
    deleted (no title), archived or no longer Open for choice."""

    rank: int
    title: str | None
    available: bool


@dataclass(frozen=True)
class SubmittedTop3:
    choices: list[Choice]
    submitted_at: datetime


def is_choosable(project: Project | None) -> bool:
    return (
        project is not None
        and project.open_for_choice
        and project.status == ProjectStatus.ACTIVE.value
    )


def choosable_projects(session: Session) -> list[Project]:
    """The Projects Students may pick now, by title."""
    return list(
        session.scalars(
            select(Project)
            .where(
                Project.open_for_choice,
                Project.status == ProjectStatus.ACTIVE.value,
            )
            .order_by(func.lower(Project.title))
        )
    )


def places(session: Session) -> int:
    """How many places a Top 3 has: 3, or fewer when fewer Projects are open."""
    return min(MAX_PLACES, len(choosable_projects(session)))


def top3_of(session: Session, student_id: int) -> SubmittedTop3 | None:
    rows = session.execute(
        select(Top3Choice, Project)
        .outerjoin(Project, Top3Choice.project_id == Project.id)
        .where(Top3Choice.student_id == student_id)
        .order_by(Top3Choice.rank)
    ).all()
    if not rows:
        return None
    return SubmittedTop3(
        choices=[
            Choice(
                rank=choice.rank,
                title=project.title if project else None,
                available=is_choosable(project),
            )
            for choice, project in rows
        ],
        submitted_at=rows[0][0].submitted_at,
    )


def can_submit(session: Session, student: User) -> bool:
    return (
        student.project_id is None
        and round_state(session).is_open
        and places(session) > 0
        and top3_of(session, student.id) is None
    )


def submit_top3(session: Session, student: User, project_ids: list[int]) -> None:
    """Save the Student's ranked Top 3 (first id = 1st choice). Final: a Student
    submits once; only a Teacher's reset lets them choose again."""
    # Locked until commit, like adding a Member (which locks the Student's row).
    session.scalar(
        select(User)
        .where(User.id == student.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if student.project_id is not None:
        raise Top3ConflictError("You already have a Project.")
    if not round_state(session).is_open:
        raise Top3ConflictError("The Top 3 round is not open.")
    if top3_of(session, student.id) is not None:
        raise Top3ConflictError("You already submitted your Top 3.")
    choosable = {project.id: project for project in choosable_projects(session)}
    wanted = min(MAX_PLACES, len(choosable))
    if wanted == 0:
        raise Top3ConflictError("No Projects are open for choice yet.")
    if len(project_ids) != wanted:
        raise Top3Error(f"Choose {wanted} different Projects.")
    if len(set(project_ids)) != len(project_ids):
        raise Top3Error("Choose each Project only once.")
    for project_id in project_ids:
        if project_id not in choosable:
            project = session.get(Project, project_id)
            name = project.title if project else "That Project"
            raise Top3Error(f"{name} is not open for choice.")
    session.add_all(
        Top3Choice(student_id=student.id, rank=rank, project_id=project_id)
        for rank, project_id in enumerate(project_ids, start=1)
    )
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise Top3ConflictError("You already submitted your Top 3.") from error
