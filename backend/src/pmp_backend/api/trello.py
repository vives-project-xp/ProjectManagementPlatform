from fastapi import APIRouter
from pydantic import BaseModel

from pmp_backend.api.deps import (
    SessionDep,
    SettingsDep,
    StudentDep,
    TeacherOrSuperuserDep,
    TrelloDep,
)
from pmp_backend.services import boards

router = APIRouter(prefix="/api", tags=["trello"])


class TrelloStatusOut(BaseModel):
    connected: bool


class BoardResultOut(BaseModel):
    project_id: int
    title: str
    created: bool
    message: str


@router.get("/trello/status")
def trello_status(
    settings: SettingsDep, user: TeacherOrSuperuserDep
) -> TrelloStatusOut:
    return TrelloStatusOut(connected=boards.is_connected(settings))


@router.post("/trello/boards")
def create_boards(
    session: SessionDep,
    client: TrelloDep,
    settings: SettingsDep,
    user: TeacherOrSuperuserDep,
) -> list[BoardResultOut]:
    """Create a Workspace and board for all Projects that need one; a result per
    Project."""
    return [
        BoardResultOut(**vars(result))
        for result in boards.create_all(session, client, settings)
    ]


class CheckOut(BaseModel):
    invited: list[str]
    removed: list[str]
    updated: list[str]
    renamed: bool
    board_gone: bool
    message: str


class CheckAllOut(BaseModel):
    project_id: int
    title: str
    message: str


class PersonAccessOut(BaseModel):
    name: str
    role: str
    email: str
    status: str


class BoardAccessOut(BaseModel):
    board_url: str
    people: list[PersonAccessOut]


@router.post("/projects/{project_id}/trello/check")
def check_members(
    project_id: int,
    session: SessionDep,
    client: TrelloDep,
    settings: SettingsDep,
    user: TeacherOrSuperuserDep,
) -> CheckOut:
    result = boards.check_members(session, client, settings, project_id)
    return CheckOut(**vars(result), message=result.message)


@router.post("/trello/check-all")
def check_all_members(
    session: SessionDep,
    client: TrelloDep,
    settings: SettingsDep,
    user: TeacherOrSuperuserDep,
) -> list[CheckAllOut]:
    return [
        CheckAllOut(project_id=project.id, title=project.title, message=message)
        for project, message in boards.check_all(session, client, settings)
    ]


@router.get("/projects/{project_id}/trello")
def board_access(
    project_id: int,
    session: SessionDep,
    client: TrelloDep,
    settings: SettingsDep,
    user: TeacherOrSuperuserDep,
) -> BoardAccessOut:
    url, people = boards.people_access(session, client, settings, project_id)
    return BoardAccessOut(
        board_url=url, people=[PersonAccessOut(**vars(person)) for person in people]
    )


class StudentAccessOut(BaseModel):
    board_url: str | None
    status: str
    email: str


@router.get("/my-project/trello")
def my_board(
    session: SessionDep, client: TrelloDep, settings: SettingsDep, student: StudentDep
) -> StudentAccessOut:
    return StudentAccessOut(
        **vars(boards.student_access(session, client, settings, student))
    )
