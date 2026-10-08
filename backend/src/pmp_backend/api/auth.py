from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel

from pmp_backend.api.deps import SessionDep, TemporaryPasswordUserDep, get_settings
from pmp_backend.api.schemas import UserOut
from pmp_backend.models import User
from pmp_backend.security import issue_token
from pmp_backend.services import auth
from pmp_backend.settings import Settings

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginIn(BaseModel):
    email: str
    password: str


class LoginOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


def login_out(user: User, settings: Settings) -> LoginOut:
    """A fresh token for this User, as every way of logging in returns it."""
    token = issue_token(
        user.id,
        user.role,
        settings.jwt_secret,
        timedelta(minutes=settings.token_lifetime_minutes),
    )
    return LoginOut(access_token=token, user=UserOut.model_validate(user))


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str


@router.post("/login")
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
    return login_out(user, settings)


@router.get("/me")
def me(user: TemporaryPasswordUserDep) -> UserOut:
    return UserOut.model_validate(user)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
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


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(user: TemporaryPasswordUserDep) -> Response:
    # Tokens are stateless; the frontend forgets the token. Kept as an explicit
    # endpoint so logging out works the same way for every client.
    return Response(status_code=status.HTTP_204_NO_CONTENT)
