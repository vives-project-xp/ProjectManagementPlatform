from typing import Annotated, Literal

from fastapi import APIRouter, Form, Response, UploadFile, status
from pydantic import BaseModel, ConfigDict, StringConstraints

from pmp_backend.api.deps import GitHubDep, SessionDep, SuperuserDep
from pmp_backend.api.github import GitHubUsernameIn
from pmp_backend.api.schemas import UserOut
from pmp_backend.domain import Role, Year
from pmp_backend.services import users

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


class UserCreateIn(BaseModel):
    role: Literal["teacher", "student"]
    first_name: Name
    last_name: Name
    email: Email
    # No password: the platform generates the Temporary password (#56).
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


class TemporaryPasswordOut(BaseModel):
    """A generated Temporary password, shown once; only its hash is kept."""

    temporary_password: str


class UserCreatedOut(UserOut):
    temporary_password: str


class ImportedUserOut(BaseModel):
    id: int
    first_name: str
    last_name: str
    email: str
    temporary_password: str


class SkippedLineOut(BaseModel):
    line: int
    email: str | None
    reason: str


class ImportOut(BaseModel):
    created: list[ImportedUserOut]
    skipped: list[SkippedLineOut]


MAX_IMPORT_BYTES = 1024 * 1024


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
) -> UserCreatedOut:
    user, password = users.create_user(
        session,
        role=Role(body.role),
        first_name=body.first_name,
        last_name=body.last_name,
        email=body.email,
        programme=body.programme,
        year=body.year,
    )
    return UserCreatedOut(
        **UserOut.model_validate(user).model_dump(), temporary_password=password
    )


@router.post("/import")
def import_users(
    file: UploadFile,
    role: Annotated[Literal["teacher", "student"], Form()],
    session: SessionDep,
    superuser: SuperuserDep,
    programme: Annotated[str | None, Form()] = None,
    year: Annotated[Year | None, Form()] = None,
) -> ImportOut:
    """One User per `Firstname,Lastname,email` line, Role, Programme and Year
    the same for the whole file (#56)."""
    content = file.file.read(MAX_IMPORT_BYTES + 1)
    if len(content) > MAX_IMPORT_BYTES:
        raise users.UserError("The file is larger than 1 MB.")
    created, skipped = users.import_users(
        session, content, role=Role(role), programme=programme, year=year
    )
    return ImportOut(
        created=[
            ImportedUserOut(
                id=item.user.id,
                first_name=item.user.first_name,
                last_name=item.user.last_name,
                email=item.user.email,
                temporary_password=item.temporary_password,
            )
            for item in created
        ],
        skipped=[
            SkippedLineOut(line=item.line, email=item.email, reason=item.reason)
            for item in skipped
        ],
    )


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


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: int, session: SessionDep, superuser: SuperuserDep) -> Response:
    users.delete_user(session, user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{user_id}/reset-password")
def reset_password(
    user_id: int, session: SessionDep, superuser: SuperuserDep
) -> TemporaryPasswordOut:
    return TemporaryPasswordOut(
        temporary_password=users.reset_password(session, user_id)
    )


@router.put("/{user_id}/github-username")
def set_github_username(
    user_id: int,
    body: GitHubUsernameIn,
    session: SessionDep,
    client: GitHubDep,
    superuser: SuperuserDep,
) -> UserOut:
    user = users.set_github_username(session, client, user_id, body.github_username)
    return UserOut.model_validate(user)
