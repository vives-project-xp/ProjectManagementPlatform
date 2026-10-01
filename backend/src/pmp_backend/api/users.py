from typing import Annotated, Literal

from fastapi import APIRouter, Response, status
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from pmp_backend.api.deps import SessionDep, SuperuserDep
from pmp_backend.api.schemas import UserOut
from pmp_backend.domain import Role, Year
from pmp_backend.services import users
from pmp_backend.services.auth import MIN_PASSWORD_LENGTH

router = APIRouter(prefix="/api/users", tags=["users"])

Name = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]
Email = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
    ),
]
TemporaryPassword = Annotated[str, Field(min_length=MIN_PASSWORD_LENGTH)]


class UserCreateIn(BaseModel):
    role: Literal["teacher", "student"]
    first_name: Name
    last_name: Name
    email: Email
    temporary_password: TemporaryPassword
    programme: Name | None = None
    year: Year | None = None


class UserEditIn(BaseModel):
    # No `role`: a User's Role is fixed at creation, so sending one is refused.
    model_config = ConfigDict(extra="forbid")

    first_name: Name
    last_name: Name
    email: Email
    programme: Name | None = None
    year: Year | None = None


class ResetPasswordIn(BaseModel):
    temporary_password: TemporaryPassword


@router.get("")
def list_users(
    session: SessionDep,
    superuser: SuperuserDep,
    role: Role | None = None,
    active: bool | None = None,
) -> list[UserOut]:
    found = users.list_users(session, role=role, active=active)
    return [UserOut.model_validate(user) for user in found]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_user(
    body: UserCreateIn, session: SessionDep, superuser: SuperuserDep
) -> UserOut:
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
    return UserOut.model_validate(user)


@router.get("/{user_id}")
def get_user(user_id: int, session: SessionDep, superuser: SuperuserDep) -> UserOut:
    return UserOut.model_validate(users.get_user(session, user_id))


@router.put("/{user_id}")
def update_user(
    user_id: int, body: UserEditIn, session: SessionDep, superuser: SuperuserDep
) -> UserOut:
    user = users.update_user(session, user_id, **body.model_dump())
    return UserOut.model_validate(user)


@router.post("/{user_id}/deactivate")
def deactivate_user(
    user_id: int, session: SessionDep, superuser: SuperuserDep
) -> UserOut:
    return UserOut.model_validate(users.deactivate_user(session, user_id, superuser))


@router.post("/{user_id}/reactivate")
def reactivate_user(
    user_id: int, session: SessionDep, superuser: SuperuserDep
) -> UserOut:
    return UserOut.model_validate(users.reactivate_user(session, user_id))


@router.post("/{user_id}/reset-password", status_code=status.HTTP_204_NO_CONTENT)
def reset_password(
    user_id: int, body: ResetPasswordIn, session: SessionDep, superuser: SuperuserDep
) -> Response:
    users.reset_password(session, user_id, body.temporary_password)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
