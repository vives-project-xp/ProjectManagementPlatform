from typing import Annotated

from fastapi import APIRouter, Response, status
from pydantic import BaseModel, ConfigDict, StringConstraints

from pmp_backend.api.deps import CurrentUserDep, SessionDep, SuperuserDep
from pmp_backend.services import programmes

router = APIRouter(prefix="/api/programmes", tags=["programmes"])


class ProgrammeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class ProgrammeIn(BaseModel):
    name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
    ]


@router.get("")
def list_programmes(session: SessionDep, user: CurrentUserDep) -> list[ProgrammeOut]:
    """The Programmes to choose from in forms and filters (ADR 0004)."""
    return [
        ProgrammeOut.model_validate(programme)
        for programme in programmes.list_programmes(session)
    ]


@router.post("", status_code=status.HTTP_201_CREATED)
def add_programme(
    body: ProgrammeIn, session: SessionDep, superuser: SuperuserDep
) -> ProgrammeOut:
    return ProgrammeOut.model_validate(programmes.add_programme(session, body.name))


@router.put("/{programme_id}")
def rename_programme(
    programme_id: int, body: ProgrammeIn, session: SessionDep, superuser: SuperuserDep
) -> ProgrammeOut:
    programme = programmes.rename_programme(session, programme_id, body.name)
    return ProgrammeOut.model_validate(programme)


@router.delete("/{programme_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_programme(
    programme_id: int, session: SessionDep, superuser: SuperuserDep
) -> Response:
    programmes.remove_programme(session, programme_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
