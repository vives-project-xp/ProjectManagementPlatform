from fastapi import APIRouter
from pydantic import BaseModel

from pmp_backend.api.deps import (
    SessionDep,
    SettingsDep,
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
