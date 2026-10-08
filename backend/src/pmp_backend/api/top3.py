from datetime import datetime

from fastapi import APIRouter
from pydantic import AwareDatetime, BaseModel

from pmp_backend.api.deps import SessionDep, StudentDep, TeacherOrSuperuserDep
from pmp_backend.models import Project
from pmp_backend.services import top3
from pmp_backend.services.top3 import RoundState

router = APIRouter(prefix="/api", tags=["top3"])


class RoundOut(BaseModel):
    deadline: datetime | None
    is_open: bool

    @classmethod
    def of(cls, state: RoundState) -> "RoundOut":
        return cls(deadline=state.deadline, is_open=state.is_open)


class DeadlineIn(BaseModel):
    # With a time zone, so "23:59" is never misread as UTC.
    deadline: AwareDatetime


@router.get("/top3/round")
def get_round(session: SessionDep, user: TeacherOrSuperuserDep) -> RoundOut:
    return RoundOut.of(top3.round_state(session))


@router.put("/top3/round")
def set_deadline(
    body: DeadlineIn, session: SessionDep, user: TeacherOrSuperuserDep
) -> RoundOut:
    return RoundOut.of(top3.set_deadline(session, body.deadline))


@router.post("/top3/round/close")
def close_round(session: SessionDep, user: TeacherOrSuperuserDep) -> RoundOut:
    return RoundOut.of(top3.close_round(session))


@router.post("/top3/round/new")
def start_new_round(
    body: DeadlineIn, session: SessionDep, user: TeacherOrSuperuserDep
) -> RoundOut:
    return RoundOut.of(top3.start_new_round(session, body.deadline))


class ChoosableProjectOut(BaseModel):
    """What a Student sees of an open Project; never how often it was chosen."""

    id: int
    title: str
    description: str | None
    product_owner: str
    team_size_min: int
    team_size_max: int
    photo_version: int | None

    @classmethod
    def of(cls, project: Project) -> "ChoosableProjectOut":
        return cls(
            id=project.id,
            title=project.title,
            description=project.description,
            product_owner=project.product_owner.full_name,
            team_size_min=project.team_size_min,
            team_size_max=project.team_size_max,
            photo_version=project.photo_version,
        )


class ChoiceOut(BaseModel):
    rank: int
    title: str | None
    available: bool


class MyTop3Out(BaseModel):
    round: RoundOut
    # Whether the Student can submit now (round open, no Project, no Top 3 yet).
    can_submit: bool
    places: int
    projects: list[ChoosableProjectOut]
    top3: list[ChoiceOut] | None
    submitted_at: datetime | None


class Top3In(BaseModel):
    # Ranked: the first id is the 1st choice.
    project_ids: list[int]


@router.get("/my-top3")
def my_top3(session: SessionDep, student: StudentDep) -> MyTop3Out:
    submitted = top3.top3_of(session, student.id)
    return MyTop3Out(
        round=RoundOut.of(top3.round_state(session)),
        can_submit=top3.can_submit(session, student),
        places=top3.places(session),
        projects=[
            ChoosableProjectOut.of(project)
            for project in top3.choosable_projects(session)
        ],
        top3=[ChoiceOut(**vars(choice)) for choice in submitted.choices]
        if submitted
        else None,
        submitted_at=submitted.submitted_at if submitted else None,
    )


@router.post("/my-top3")
def submit_top3(body: Top3In, session: SessionDep, student: StudentDep) -> MyTop3Out:
    top3.submit_top3(session, student, body.project_ids)
    return my_top3(session, student)
