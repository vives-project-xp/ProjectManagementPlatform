from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Response, status
from pydantic import AwareDatetime, BaseModel, StringConstraints

from pmp_backend.api.deps import (
    SessionDep,
    StudentDep,
    TeacherOrSuperuserDep,
)
from pmp_backend.models import Deadline
from pmp_backend.services import planning
from pmp_backend.services.planning import DeadlineFields

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


@router.get("/planning")
def upcoming(
    session: SessionDep, user: TeacherOrSuperuserDep, mine: bool = False
) -> list[DeadlineOut]:
    """Today's and later deadlines across Active Projects; with `mine`, only the
    Projects of which the User is the Product Owner (and those for every Project)."""
    return _out(planning.upcoming(session, user.id if mine else None))


@router.get("/my-project/planning")
def my_planning(session: SessionDep, student: StudentDep) -> list[DeadlineOut]:
    """The deadlines of the Student's Project, earliest first (none without one)."""
    if student.project is None:
        return []
    return _out(planning.project_deadlines(session, student.project))
