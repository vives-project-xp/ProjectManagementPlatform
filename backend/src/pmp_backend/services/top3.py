"""The Top 3 (spec #37): which Projects Students may choose, and the one round
in which they choose."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from pmp_backend.domain import ProjectStatus, Role, Year
from pmp_backend.errors import Conflict, NotFound, Refused
from pmp_backend.models import Project, Top3Choice, Top3Round, User
from pmp_backend.services import users
from pmp_backend.services.projects import changeable_project

MAX_PLACES = 3


class Top3Error(Refused):
    """A Top 3 change was refused; the message is fit to show."""


class Top3ConflictError(Top3Error, Conflict):
    pass


class Top3NotFoundError(Top3Error, NotFound):
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
    project_id: int | None
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


def _top3s(session: Session, student_ids: list[int]) -> dict[int, SubmittedTop3]:
    """The submitted Top 3 of each of these Students that has one."""
    rows = session.execute(
        select(Top3Choice, Project)
        .outerjoin(Project, Top3Choice.project_id == Project.id)
        .where(Top3Choice.student_id.in_(student_ids))
        .order_by(Top3Choice.student_id, Top3Choice.rank)
    ).all()
    found: dict[int, SubmittedTop3] = {}
    for choice, project in rows:
        top3 = found.setdefault(
            choice.student_id,
            SubmittedTop3(choices=[], submitted_at=choice.submitted_at),
        )
        top3.choices.append(
            Choice(
                rank=choice.rank,
                project_id=choice.project_id,
                title=project.title if project else None,
                available=is_choosable(project),
            )
        )
    return found


def top3_of(session: Session, student_id: int) -> SubmittedTop3 | None:
    return _top3s(session, [student_id]).get(student_id)


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


# The overview (Teachers and the Superuser)


@dataclass(frozen=True)
class StudentTop3:
    student: User
    top3: SubmittedTop3 | None


@dataclass(frozen=True)
class ProjectSummary:
    """How many active Students put this open Project 1st, 2nd and 3rd."""

    project: Project
    first: int
    second: int
    third: int


def overview(
    session: Session,
    *,
    programme: str | None = None,
    year: Year | None = None,
    without_top3: bool = False,
) -> list[StudentTop3]:
    """Every active Student, by name, with their Top 3 (or None)."""
    students = [
        student
        for student in users.list_students(session, programme=programme, year=year)
        if student.is_active
    ]
    top3s = _top3s(session, [student.id for student in students])
    rows = [StudentTop3(student, top3s.get(student.id)) for student in students]
    if without_top3:
        rows = [row for row in rows if row.top3 is None]
    return rows


def summary(session: Session) -> list[ProjectSummary]:
    """For each Project open for choice, its count per rank (active Students)."""
    counts = session.execute(
        select(Top3Choice.project_id, Top3Choice.rank, func.count())
        .join(User, Top3Choice.student_id == User.id)
        .where(User.is_active)
        .group_by(Top3Choice.project_id, Top3Choice.rank)
    ).all()
    by_project: dict[tuple[int | None, int], int] = {
        (project_id, rank): count for project_id, rank, count in counts
    }
    return [
        ProjectSummary(
            project=project,
            first=by_project.get((project.id, 1), 0),
            second=by_project.get((project.id, 2), 0),
            third=by_project.get((project.id, 3), 0),
        )
        for project in choosable_projects(session)
    ]


def reset_top3(session: Session, student_id: int) -> None:
    """Clear one Student's Top 3 so they can choose again; only while open."""
    student = session.scalar(
        select(User)
        .where(User.id == student_id, User.role == Role.STUDENT.value)
        .with_for_update()
    )
    if student is None:
        raise Top3NotFoundError("This Student does not exist.")
    if not round_state(session).is_open:
        raise Top3ConflictError("The Top 3 round is closed, so a Top 3 can't be reset.")
    if top3_of(session, student.id) is None:
        raise Top3NotFoundError(f"{student.full_name} has no Top 3.")
    session.execute(delete(Top3Choice).where(Top3Choice.student_id == student.id))
    session.commit()
