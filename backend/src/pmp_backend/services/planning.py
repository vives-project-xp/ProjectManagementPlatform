"""Deadlines (spec #68): for one Project or for every Active Project, and what is
coming up, in Belgian time."""

from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from pmp_backend.domain import ProjectStatus
from pmp_backend.errors import NotFound, Refused
from pmp_backend.models import Deadline, Project
from pmp_backend.services.projects import changeable_project, get_project

# "Today", "upcoming" and "earlier" are decided in Belgian time.
BRUSSELS = ZoneInfo("Europe/Brussels")

TODAY, UPCOMING, EARLIER = "today", "upcoming", "earlier"


class PlanningError(Refused):
    """A planning change was refused; the message is fit to show."""


class DeadlineNotFoundError(PlanningError, NotFound):
    pass


@dataclass(frozen=True)
class DeadlineFields:
    title: str
    due_at: datetime
    description: str | None


def today() -> date:
    return datetime.now(BRUSSELS).date()


def when(moment: datetime) -> str:
    """Whether a moment falls today, later, or before today, in Belgian time."""
    day = moment.astimezone(BRUSSELS).date()
    if day == today():
        return TODAY
    return UPCOMING if day > today() else EARLIER


def _start_of_today() -> datetime:
    return datetime.combine(today(), datetime.min.time(), tzinfo=BRUSSELS)


def _apply(deadline: Deadline, fields: DeadlineFields) -> None:
    deadline.title = fields.title
    deadline.due_at = fields.due_at
    deadline.description = fields.description or None


def add_deadline(
    session: Session, project_id: int | None, fields: DeadlineFields
) -> Deadline:
    """A Deadline for one Project (refused when it is archived), or for every
    Active Project when `project_id` is None."""
    if project_id is not None:
        changeable_project(session, project_id)
    deadline = Deadline(project_id=project_id)
    _apply(deadline, fields)
    session.add(deadline)
    session.commit()
    return deadline


def _changeable_deadline(session: Session, deadline_id: int) -> Deadline:
    deadline = session.get(Deadline, deadline_id)
    if deadline is None:
        raise DeadlineNotFoundError("This deadline does not exist.")
    if deadline.project_id is not None:
        # Archived Projects keep their deadlines, read-only.
        changeable_project(session, deadline.project_id)
    return deadline


def update_deadline(
    session: Session, deadline_id: int, fields: DeadlineFields
) -> Deadline:
    deadline = _changeable_deadline(session, deadline_id)
    _apply(deadline, fields)
    session.commit()
    return deadline


def delete_deadline(session: Session, deadline_id: int) -> None:
    session.delete(_changeable_deadline(session, deadline_id))
    session.commit()


def project_deadlines(session: Session, project: Project) -> list[Deadline]:
    """The Project's own deadlines and, while it is Active, the ones for every
    Active Project, earliest first."""
    applies = Deadline.project_id == project.id
    if project.status == ProjectStatus.ACTIVE.value:
        applies = or_(applies, Deadline.project_id.is_(None))
    return list(
        session.scalars(select(Deadline).where(applies).order_by(Deadline.due_at))
    )


def deadlines_of(session: Session, project_id: int) -> list[Deadline]:
    return project_deadlines(session, get_project(session, project_id))


def upcoming(session: Session, owner_id: int | None = None) -> list[Deadline]:
    """Today's and later deadlines of Active Projects and for every Project,
    earliest first; with `owner_id`, only those of that Product Owner's Projects
    (and the ones for every Project)."""
    active = select(Project.id).where(Project.status == ProjectStatus.ACTIVE.value)
    if owner_id is not None:
        active = active.where(Project.product_owner_id == owner_id)
    return list(
        session.scalars(
            select(Deadline)
            .where(
                Deadline.due_at >= _start_of_today(),
                or_(Deadline.project_id.is_(None), Deadline.project_id.in_(active)),
            )
            .order_by(Deadline.due_at)
        )
    )
