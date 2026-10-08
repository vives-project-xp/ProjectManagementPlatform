from datetime import datetime

from fastapi import APIRouter
from pydantic import AwareDatetime, BaseModel

from pmp_backend.api.deps import SessionDep, TeacherOrSuperuserDep
from pmp_backend.services import top3
from pmp_backend.services.top3 import RoundState

router = APIRouter(prefix="/api/top3", tags=["top3"])


class RoundOut(BaseModel):
    deadline: datetime | None
    is_open: bool

    @classmethod
    def of(cls, state: RoundState) -> "RoundOut":
        return cls(deadline=state.deadline, is_open=state.is_open)


class DeadlineIn(BaseModel):
    # With a time zone, so "23:59" is never misread as UTC.
    deadline: AwareDatetime


@router.get("/round")
def get_round(session: SessionDep, user: TeacherOrSuperuserDep) -> RoundOut:
    return RoundOut.of(top3.round_state(session))


@router.put("/round")
def set_deadline(
    body: DeadlineIn, session: SessionDep, user: TeacherOrSuperuserDep
) -> RoundOut:
    return RoundOut.of(top3.set_deadline(session, body.deadline))


@router.post("/round/close")
def close_round(session: SessionDep, user: TeacherOrSuperuserDep) -> RoundOut:
    return RoundOut.of(top3.close_round(session))


@router.post("/round/new")
def start_new_round(
    body: DeadlineIn, session: SessionDep, user: TeacherOrSuperuserDep
) -> RoundOut:
    return RoundOut.of(top3.start_new_round(session, body.deadline))
