from datetime import date, datetime, time
from typing import Annotated

from fastapi import APIRouter, Response, status
from pydantic import AwareDatetime, BaseModel, Field, StringConstraints

from pmp_backend.api.deps import (
    SessionDep,
    StudentDep,
    TeacherOrSuperuserDep,
)
from pmp_backend.models import Deadline, WeeklySlot
from pmp_backend.services import planning
from pmp_backend.services.planning import (
    AgendaItem,
    DeadlineFields,
    MeetingFields,
    SlotFields,
)

router = APIRouter(prefix="/api", tags=["planning"])


class DeadlineIn(BaseModel):
    title: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
    ]
    # With its time zone; the frontend sends Belgian time.
    due_at: AwareDatetime
    description: (
        Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)] | None
    ) = None

    def fields(self) -> DeadlineFields:
        return DeadlineFields(self.title, self.due_at, self.description)


class DeadlineOut(BaseModel):
    id: int
    # None: for every Active Project.
    project_id: int | None
    project_title: str | None
    title: str
    due_at: datetime
    description: str | None
    # "today", "upcoming" or "earlier", in Belgian time.
    when: str

    @classmethod
    def of(cls, deadline: Deadline) -> "DeadlineOut":
        return cls(
            id=deadline.id,
            project_id=deadline.project_id,
            project_title=deadline.project.title if deadline.project else None,
            title=deadline.title,
            due_at=deadline.due_at,
            description=deadline.description,
            when=planning.when(deadline.due_at),
        )


def _out(deadlines: list[Deadline]) -> list[DeadlineOut]:
    return [DeadlineOut.of(deadline) for deadline in deadlines]


@router.get("/projects/{project_id}/deadlines")
def project_deadlines(
    project_id: int, session: SessionDep, user: TeacherOrSuperuserDep
) -> list[DeadlineOut]:
    """The Project's own deadlines and, while it is Active, those for every
    Project, earliest first."""
    return _out(planning.deadlines_of(session, project_id))


@router.post("/projects/{project_id}/deadlines", status_code=status.HTTP_201_CREATED)
def add_project_deadline(
    project_id: int, body: DeadlineIn, session: SessionDep, user: TeacherOrSuperuserDep
) -> DeadlineOut:
    return DeadlineOut.of(planning.add_deadline(session, project_id, body.fields()))


@router.post("/deadlines", status_code=status.HTTP_201_CREATED)
def add_deadline_for_all(
    body: DeadlineIn, session: SessionDep, user: TeacherOrSuperuserDep
) -> DeadlineOut:
    """A deadline for every Active Project."""
    return DeadlineOut.of(planning.add_deadline(session, None, body.fields()))


@router.put("/deadlines/{deadline_id}")
def update_deadline(
    deadline_id: int, body: DeadlineIn, session: SessionDep, user: TeacherOrSuperuserDep
) -> DeadlineOut:
    return DeadlineOut.of(planning.update_deadline(session, deadline_id, body.fields()))


@router.delete("/deadlines/{deadline_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_deadline(
    deadline_id: int, session: SessionDep, user: TeacherOrSuperuserDep
) -> Response:
    planning.delete_deadline(session, deadline_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# Meetings and the Weekly slot

Place = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)
]


class MeetingIn(BaseModel):
    starts_at: AwareDatetime
    ends_at: AwareDatetime
    # A room, or a link to an online meeting.
    place: Place
    note: (
        Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)] | None
    ) = None

    def fields(self) -> MeetingFields:
        return MeetingFields(self.starts_at, self.ends_at, self.place, self.note)


class SlotIn(BaseModel):
    # 0 is Monday.
    weekday: Annotated[int, Field(ge=0, le=6)]
    # Belgian time.
    starts: time
    ends: time
    place: Place

    def fields(self) -> SlotFields:
        return SlotFields(self.weekday, self.starts, self.ends, self.place)


class SlotOut(BaseModel):
    project_id: int
    project_title: str
    weekday: int
    weekday_name: str
    starts: time
    ends: time
    place: str
    # Today's and later skipped dates.
    skipped: list[date]

    @classmethod
    def of(cls, slot: WeeklySlot) -> "SlotOut":
        return cls(
            project_id=slot.project_id,
            project_title=slot.project.title,
            weekday=slot.weekday,
            weekday_name=planning.WEEKDAYS[slot.weekday],
            starts=slot.starts,
            ends=slot.ends,
            place=slot.place,
            skipped=[s.day for s in slot.skips if s.day >= planning.today()],
        )


class AgendaItemOut(BaseModel):
    # "deadline", "meeting" or "weekly".
    kind: str
    # The deadline's or meeting's id; the Project's id for a weekly meeting.
    id: int
    # None: a deadline for every Active Project.
    project_id: int | None
    project_title: str | None
    title: str
    starts_at: datetime
    # None for a deadline.
    ends_at: datetime | None
    place: str | None
    details: str | None
    # "today", "upcoming" or "earlier", in Belgian time.
    when: str

    @classmethod
    def of(cls, item: AgendaItem) -> "AgendaItemOut":
        return cls(**vars(item), when=planning.when(item.starts_at))


class ProjectPlanningOut(BaseModel):
    items: list[AgendaItemOut]
    weekly_slot: SlotOut | None

    @classmethod
    def of(
        cls, agenda: tuple[list[AgendaItem], WeeklySlot | None]
    ) -> "ProjectPlanningOut":
        items, slot = agenda
        return cls(
            items=[AgendaItemOut.of(item) for item in items],
            weekly_slot=SlotOut.of(slot) if slot else None,
        )


class OverviewOut(BaseModel):
    items: list[AgendaItemOut]
    weekly_slots: list[SlotOut]


@router.get("/projects/{project_id}/planning")
def project_planning(
    project_id: int, session: SessionDep, user: TeacherOrSuperuserDep
) -> ProjectPlanningOut:
    """The Project's deadlines (own and for every Project), meetings and this
    week's weekly meetings, earliest first, and its Weekly slot."""
    return ProjectPlanningOut.of(planning.agenda_of(session, project_id))


@router.get("/planning")
def overview(
    session: SessionDep, user: TeacherOrSuperuserDep, mine: bool = False
) -> OverviewOut:
    """What is coming up across Active Projects; with `mine`, only the Projects of
    which the User is the Product Owner (and the deadlines for every Project)."""
    items, slots = planning.overview(session, user.id if mine else None)
    return OverviewOut(
        items=[AgendaItemOut.of(item) for item in items],
        weekly_slots=[SlotOut.of(slot) for slot in slots],
    )


@router.get("/my-project/planning")
def my_planning(session: SessionDep, student: StudentDep) -> ProjectPlanningOut:
    """The Student's Project's planning (empty without a Project)."""
    if student.project is None:
        return ProjectPlanningOut(items=[], weekly_slot=None)
    return ProjectPlanningOut.of(planning.project_agenda(session, student.project))


@router.post("/projects/{project_id}/meetings", status_code=status.HTTP_201_CREATED)
def add_meeting(
    project_id: int, body: MeetingIn, session: SessionDep, user: TeacherOrSuperuserDep
) -> AgendaItemOut:
    meeting = planning.add_meeting(session, project_id, body.fields())
    return AgendaItemOut.of(planning.meeting_item(meeting))


@router.put("/meetings/{meeting_id}")
def update_meeting(
    meeting_id: int, body: MeetingIn, session: SessionDep, user: TeacherOrSuperuserDep
) -> AgendaItemOut:
    meeting = planning.update_meeting(session, meeting_id, body.fields())
    return AgendaItemOut.of(planning.meeting_item(meeting))


@router.delete("/meetings/{meeting_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_meeting(
    meeting_id: int, session: SessionDep, user: TeacherOrSuperuserDep
) -> Response:
    planning.delete_meeting(session, meeting_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/projects/{project_id}/weekly-slot")
def set_weekly_slot(
    project_id: int, body: SlotIn, session: SessionDep, user: TeacherOrSuperuserDep
) -> SlotOut:
    return SlotOut.of(planning.set_weekly_slot(session, project_id, body.fields()))


@router.delete(
    "/projects/{project_id}/weekly-slot", status_code=status.HTTP_204_NO_CONTENT
)
def clear_weekly_slot(
    project_id: int, session: SessionDep, user: TeacherOrSuperuserDep
) -> Response:
    planning.clear_weekly_slot(session, project_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/projects/{project_id}/weekly-slot/skips/{day}")
def skip_date(
    project_id: int, day: date, session: SessionDep, user: TeacherOrSuperuserDep
) -> SlotOut:
    return SlotOut.of(planning.skip_date(session, project_id, day))


@router.delete("/projects/{project_id}/weekly-slot/skips/{day}")
def unskip_date(
    project_id: int, day: date, session: SessionDep, user: TeacherOrSuperuserDep
) -> SlotOut:
    return SlotOut.of(planning.unskip_date(session, project_id, day))
