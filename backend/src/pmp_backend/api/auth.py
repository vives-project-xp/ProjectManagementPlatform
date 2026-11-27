from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel

from pmp_backend.api.deps import SessionDep, TemporaryPasswordUserDep, get_settings
from pmp_backend.api.schemas import UserOut
from pmp_backend.models import User
from pmp_backend.security import issue_token
from pmp_backend.services import auth, break_glass, vives_login
from pmp_backend.settings import Settings

router = APIRouter(prefix="/api/auth", tags=["auth"])

VIVES_ONLY = "Log in with VIVES."


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
    request: Request,
    session: SessionDep,
    settings: Annotated[Settings, Depends(get_settings)],
) -> LoginOut:
    # VIVES login on: no password login on the site at all (ADR 0011).
    if vives_login.is_on(session):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=VIVES_ONLY)
    guard: auth.LoginGuard = request.app.state.login_guard
    # Checked before the password, so a locked email learns nothing more.
    if guard.is_locked(body.email):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed attempts. Try again in 15 minutes.",
        )
    user = auth.authenticate(session, body.email, body.password)
    if user is None:
        guard.failed(body.email)
        # One message for unknown email, wrong password and Deactivated User alike.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
        )
    guard.succeeded(body.email)
    return login_out(user, settings)


@router.get("/me")
def me(user: TemporaryPasswordUserDep) -> UserOut:
    return UserOut.model_validate(user)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    body: ChangePasswordIn, user: TemporaryPasswordUserDep, session: SessionDep
) -> Response:
    if vives_login.is_on(session):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=VIVES_ONLY)
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


# VIVES login (spec #160, ADR 0011)


class VivesStartOut(BaseModel):
    # False until VIVES login is switched on: the login page shows no button.
    configured: bool
    authorization_endpoint: str | None = None
    client_id: str | None = None
    scope: str | None = None
    redirect_uri: str | None = None


@router.get("/vives/start")
def vives_start(
    request: Request,
    session: SessionDep,
    settings: Annotated[Settings, Depends(get_settings)],
) -> VivesStartOut:
    """What the frontend needs to send the browser to Authentik (it adds its
    own state, nonce and PKCE challenge); only once VIVES login is switched
    on (#162)."""
    config = vives_login.config_from(settings, session)
    if config is None or not vives_login.is_on(session):
        return VivesStartOut(configured=False)
    found = vives_login.start(request.app.state.oidc, config, settings)
    return VivesStartOut(configured=True, **vars(found))


class VivesLoginIn(BaseModel):
    code: str
    code_verifier: str
    nonce: str


@router.post("/vives")
def vives(
    body: VivesLoginIn,
    request: Request,
    session: SessionDep,
    settings: Annotated[Settings, Depends(get_settings)],
) -> LoginOut:
    """Finish a VIVES login: the code Authentik gave the browser, the PKCE
    verifier and nonce the frontend kept; the usual session token."""
    config = vives_login.config_from(settings, session)
    if config is None or not vives_login.is_on(session):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="VIVES login isn't on."
        )
    user = vives_login.log_in(
        session,
        request.app.state.oidc,
        config,
        settings,
        code=body.code,
        code_verifier=body.code_verifier,
        nonce=body.nonce,
    )
    return login_out(user, settings)


class BreakGlassIn(BaseModel):
    code: str


@router.post("/break-glass")
def use_break_glass(
    body: BreakGlassIn,
    session: SessionDep,
    settings: Annotated[Settings, Depends(get_settings)],
) -> LoginOut:
    """Log in with a one-time Break-glass link made on the VM (#163)."""
    return login_out(break_glass.use(session, body.code), settings)
