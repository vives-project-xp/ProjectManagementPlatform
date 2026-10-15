"""Deadlines, Meetings and Weekly slots (spec #68), and what is coming up, in
Belgian time."""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from pmp_backend.domain import ProjectStatus
from pmp_backend.errors import Conflict, NotFound, Refused
from pmp_backend.models import (
    Deadline,
    Meeting,
    Project,
    WeeklySlot,
    WeeklySlotSkip,
)
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


# Meetings and the Weekly slot


class MeetingNotFoundError(PlanningError, NotFound):
    pass


class PlanningConflictError(PlanningError, Conflict):
    pass


WEEKDAYS = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)
# Weekly slot occurrences are shown for today and the six days after it.
WEEK = 7


@dataclass(frozen=True)
class MeetingFields:
    starts_at: datetime
    ends_at: datetime
    place: str
    note: str | None


@dataclass(frozen=True)
class SlotFields:
    weekday: int
    starts: time
    ends: time
    place: str


def _apply_meeting(meeting: Meeting, fields: MeetingFields) -> None:
    if fields.ends_at <= fields.starts_at:
        raise PlanningError("A meeting must end after it starts.")
    meeting.starts_at = fields.starts_at
    meeting.ends_at = fields.ends_at
    meeting.place = fields.place
    meeting.note = fields.note or None


def add_meeting(session: Session, project_id: int, fields: MeetingFields) -> Meeting:
    changeable_project(session, project_id)
    meeting = Meeting(project_id=project_id)
    _apply_meeting(meeting, fields)
    session.add(meeting)
    session.commit()
    return meeting


def _changeable_meeting(session: Session, meeting_id: int) -> Meeting:
    meeting = session.get(Meeting, meeting_id)
    if meeting is None:
        raise MeetingNotFoundError("This meeting does not exist.")
    # Archived Projects keep their meetings, read-only.
    changeable_project(session, meeting.project_id)
    return meeting


def update_meeting(session: Session, meeting_id: int, fields: MeetingFields) -> Meeting:
    meeting = _changeable_meeting(session, meeting_id)
    _apply_meeting(meeting, fields)
    session.commit()
    return meeting


def delete_meeting(session: Session, meeting_id: int) -> None:
    session.delete(_changeable_meeting(session, meeting_id))
    session.commit()


def set_weekly_slot(
    session: Session, project_id: int, fields: SlotFields
) -> WeeklySlot:
    """Set (or change) the Project's one Weekly slot; skipped dates stay."""
    changeable_project(session, project_id)
    if fields.ends <= fields.starts:
        raise PlanningError("The weekly meeting must end after it starts.")
    slot = session.get(WeeklySlot, project_id) or WeeklySlot(project_id=project_id)
    slot.weekday = fields.weekday
    slot.starts = fields.starts
    slot.ends = fields.ends
    slot.place = fields.place
    session.add(slot)
    session.commit()
    return slot


def _changeable_slot(session: Session, project_id: int) -> WeeklySlot:
    project = changeable_project(session, project_id)
    slot = session.get(WeeklySlot, project_id)
    if slot is None:
        raise PlanningConflictError(f"{project.title} has no weekly meeting.")
    return slot


def clear_weekly_slot(session: Session, project_id: int) -> None:
    """No more Weekly slot (e.g. during exams); its skipped dates go with it."""
    session.delete(_changeable_slot(session, project_id))
    session.commit()


def skip_date(session: Session, project_id: int, day: date) -> WeeklySlot:
    """The Weekly slot doesn't take place on `day` (which must be its weekday)."""
    slot = _changeable_slot(session, project_id)
    if day.weekday() != slot.weekday:
        raise PlanningError(
            f"{day:%d/%m/%Y} isn't a {WEEKDAYS[slot.weekday]}, the day of the "
            "weekly meeting."
        )
    if day not in {skip.day for skip in slot.skips}:
        slot.skips.append(WeeklySlotSkip(day=day))
    session.commit()
    return slot


def unskip_date(session: Session, project_id: int, day: date) -> WeeklySlot:
    slot = _changeable_slot(session, project_id)
    slot.skips = [skip for skip in slot.skips if skip.day != day]
    session.commit()
    return slot


# The agenda: deadlines, meetings and Weekly slot occurrences in one list.

DEADLINE, MEETING, WEEKLY = "deadline", "meeting", "weekly"


@dataclass(frozen=True)
class AgendaItem:
    kind: str
    # The deadline's or meeting's id; the Project's id for a weekly occurrence.
    id: int
    # None: a deadline for every Active Project.
    project_id: int | None
    project_title: str | None
    title: str
    starts_at: datetime
    ends_at: datetime | None
    place: str | None
    details: str | None


def _deadline_item(deadline: Deadline) -> AgendaItem:
    return AgendaItem(
        DEADLINE,
        deadline.id,
        deadline.project_id,
        deadline.project.title if deadline.project else None,
        deadline.title,
        deadline.due_at,
        None,
        None,
        deadline.description,
    )


def meeting_item(meeting: Meeting) -> AgendaItem:
    return AgendaItem(
        MEETING,
        meeting.id,
        meeting.project_id,
        meeting.project.title,
        "Meeting",
        meeting.starts_at,
        meeting.ends_at,
        meeting.place,
        meeting.note,
    )


def occurrences(slot: WeeklySlot, first: date, days: int) -> list[AgendaItem]:
    """The Weekly slot's meetings from `first` on for `days` days, without the
    skipped dates."""
    skipped = {skip.day for skip in slot.skips}
    items = []
    for offset in range(days):
        day = first + timedelta(days=offset)
        if day.weekday() != slot.weekday or day in skipped:
            continue
        items.append(
            AgendaItem(
                WEEKLY,
                slot.project_id,
                slot.project_id,
                slot.project.title,
                "Weekly meeting",
                datetime.combine(day, slot.starts, tzinfo=BRUSSELS),
                datetime.combine(day, slot.ends, tzinfo=BRUSSELS),
                slot.place,
                None,
            )
        )
    return items


def _sorted(items: list[AgendaItem]) -> list[AgendaItem]:
    return sorted(items, key=lambda item: (item.starts_at, item.kind, item.id))


def project_agenda(
    session: Session, project: Project
) -> tuple[list[AgendaItem], WeeklySlot | None]:
    """Everything of a Project, earliest first: its own and the all-Projects
    deadlines, its meetings and, while it is Active, this week's weekly meetings;
    and its Weekly slot."""
    items = [_deadline_item(d) for d in project_deadlines(session, project)]
    meetings = session.scalars(select(Meeting).where(Meeting.project_id == project.id))
    items += [meeting_item(m) for m in meetings]
    slot = session.get(WeeklySlot, project.id)
    if slot is not None and project.status == ProjectStatus.ACTIVE.value:
        items += occurrences(slot, today(), WEEK)
    return _sorted(items), slot


def agenda_of(
    session: Session, project_id: int
) -> tuple[list[AgendaItem], WeeklySlot | None]:
    return project_agenda(session, get_project(session, project_id))


def overview(
    session: Session, owner_id: int | None = None
) -> tuple[list[AgendaItem], list[WeeklySlot]]:
    """What is coming up across Active Projects (with `owner_id`, only that
    Product Owner's, plus the all-Projects deadlines): today's and later
    deadlines and meetings, and this week's weekly meetings; and every Active
    Project's Weekly slot."""
    active = select(Project.id).where(Project.status == ProjectStatus.ACTIVE.value)
    if owner_id is not None:
        active = active.where(Project.product_owner_id == owner_id)
    items = [_deadline_item(d) for d in upcoming(session, owner_id)]
    meetings = session.scalars(
        select(Meeting).where(
            Meeting.project_id.in_(active), Meeting.ends_at >= _start_of_today()
        )
    )
    items += [meeting_item(m) for m in meetings]
    slots = list(
        session.scalars(
            select(WeeklySlot)
            .join(Project)
            .where(WeeklySlot.project_id.in_(active))
            .order_by(WeeklySlot.weekday, WeeklySlot.starts, func.lower(Project.title))
        )
    )
    for slot in slots:
        items += occurrences(slot, today(), WEEK)
    return _sorted(items), slots


def items_on(session: Session, project: Project, day: date) -> list[AgendaItem]:
    """An Active Project's deadlines (own and for every Project), meetings and
    weekly meeting on `day` (Belgian time), earliest first."""
    start = datetime.combine(day, datetime.min.time(), tzinfo=BRUSSELS)
    end = start + timedelta(days=1)
    deadlines = [
        d for d in project_deadlines(session, project) if start <= d.due_at < end
    ]
    items = [_deadline_item(d) for d in deadlines]
    meetings = session.scalars(
        select(Meeting).where(
            Meeting.project_id == project.id,
            Meeting.starts_at >= start,
            Meeting.starts_at < end,
        )
    )
    items += [meeting_item(m) for m in meetings]
    slot = session.get(WeeklySlot, project.id)
    if slot is not None:
        items += occurrences(slot, day, 1)
    return _sorted(items)
