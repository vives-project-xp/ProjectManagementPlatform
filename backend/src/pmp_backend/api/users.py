from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, StringConstraints

from pmp_backend.api.deps import SessionDep, SuperuserDep
from pmp_backend.api.schemas import UserOut
from pmp_backend.domain import Programme, Role, Year
from pmp_backend.services import users
from pmp_backend.services.auth import MIN_PASSWORD_LENGTH

router = APIRouter(prefix="/api/users", tags=["users"])

Name = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]


class UserCreateIn(BaseModel):
    role: Literal["teacher", "student"]
    first_name: Name
    last_name: Name
    email: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
        ),
    ]
    temporary_password: str = Field(min_length=MIN_PASSWORD_LENGTH)
    programme: Programme | None = None
    year: Year | None = None


@router.get("")
def list_users(session: SessionDep, superuser: SuperuserDep) -> list[UserOut]:
    return [UserOut.model_validate(user) for user in users.list_users(session)]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_user(
    body: UserCreateIn, session: SessionDep, superuser: SuperuserDep
) -> UserOut:
    try:
        user = users.create_user(
            session,
            role=Role(body.role),
            first_name=body.first_name,
            last_name=body.last_name,
            email=body.email,
            temporary_password=body.temporary_password,
            programme=body.programme,
            year=body.year,
        )
    except users.DuplicateEmailError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(error)) from error
    except users.UserError as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
        ) from error
    return UserOut.model_validate(user)
