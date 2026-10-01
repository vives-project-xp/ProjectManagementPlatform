from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel

from pmp_backend.api.deps import (
    CurrentUserDep,
    SessionDep,
    TemporaryPasswordUserDep,
    get_settings,
)
from pmp_backend.domain import Programme
from pmp_backend.models import User
from pmp_backend.security import issue_token
from pmp_backend.services import auth
from pmp_backend.settings import Settings

router = APIRouter(prefix="/api", tags=["auth"])


class UserOut(BaseModel):
    id: int
    first_name: str
    last_name: str
    email: str
    role: str
    must_change_password: bool
    programme: str | None
    year: str | None

    @classmethod
    def of(cls, user: User) -> "UserOut":
        return cls.model_validate(user, from_attributes=True)


class LoginIn(BaseModel):
    email: str
    password: str


class LoginOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str


@router.post("/auth/login")
def login(
    body: LoginIn,
    session: SessionDep,
    settings: Annotated[Settings, Depends(get_settings)],
) -> LoginOut:
    user = auth.authenticate(session, body.email, body.password)
    if user is None:
        # One message for unknown email, wrong password and Deactivated User alike.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
        )
    token = issue_token(
        user.id,
        settings.jwt_secret,
        timedelta(minutes=settings.token_lifetime_minutes),
    )
    return LoginOut(access_token=token, user=UserOut.of(user))


@router.get("/auth/me")
def me(user: TemporaryPasswordUserDep) -> UserOut:
    return UserOut.of(user)


@router.post("/auth/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    body: ChangePasswordIn, user: TemporaryPasswordUserDep, session: SessionDep
) -> Response:
    try:
        auth.change_password(session, user, body.current_password, body.new_password)
    except auth.PasswordChangeError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
        ) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(user: TemporaryPasswordUserDep) -> Response:
    # Tokens are stateless; the frontend forgets the token. Kept as an explicit
    # endpoint so logging out works the same way for every client.
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/programmes")
def programmes(user: CurrentUserDep) -> list[str]:
    return [programme.value for programme in Programme]
