"""The VIVES login screen (spec #160, #162): the Superuser connects Authentik,
tests it and switches it on. The secret never leaves the backend."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Request
from pydantic import BaseModel, StringConstraints

from pmp_backend.api.deps import SessionDep, SettingsDep, SuperuserDep
from pmp_backend.services import vives_login

router = APIRouter(prefix="/api/vives-login", tags=["vives login"])

Name = Annotated[str, StringConstraints(max_length=100)]


class ScreenOut(BaseModel):
    # Copy this into Authentik's provider.
    redirect_uri: str
    scope: str
    # AUTHENTIK_* in the server's environment sets the connection (read-only).
    from_environment: bool
    issuer_url: str | None
    client_id: str | None
    # Whether a Client secret is stored (it is never shown).
    secret_set: bool
    # Role -> Authentik group.
    groups: dict[str, str]
    programme_claim: str
    year_claim: str
    tested_at: datetime | None
    # The Role the last Setup test gave (null when it was refused).
    tested_role: str | None
    # That test was done with the settings as they are now.
    test_is_current: bool
    enabled_at: datetime | None
    enabled_by: str | None


def _screen(session, settings) -> ScreenOut:
    found = vives_login.screen(session, settings)
    session.commit()
    return ScreenOut(**vars(found))


@router.get("")
def get_screen(
    session: SessionDep, settings: SettingsDep, user: SuperuserDep
) -> ScreenOut:
    return _screen(session, settings)


class ScreenIn(BaseModel):
    issuer_url: Annotated[str, StringConstraints(max_length=500)] | None = None
    client_id: Annotated[str, StringConstraints(max_length=255)] | None = None
    # Empty or left out: the stored secret stays.
    client_secret: Annotated[str, StringConstraints(max_length=2000)] | None = None
    groups: dict[str, Name]
    programme_claim: Name
    year_claim: Name


@router.put("")
def save_screen(
    body: ScreenIn, session: SessionDep, settings: SettingsDep, user: SuperuserDep
) -> ScreenOut:
    vives_login.save(
        session,
        settings,
        issuer_url=body.issuer_url,
        client_id=body.client_id,
        client_secret=body.client_secret,
        groups=body.groups,
        programme_claim=body.programme_claim,
        year_claim=body.year_claim,
    )
    return _screen(session, settings)


class CheckOut(BaseModel):
    message: str


@router.post("/check")
def check_connection(
    request: Request, session: SessionDep, settings: SettingsDep, user: SuperuserDep
) -> CheckOut:
    """Fetch Authentik's configuration and keys: is the Issuer URL right, and
    does the server reach it?"""
    message = vives_login.check(session, request.app.state.oidc, settings)
    session.commit()
    return CheckOut(message=message)


class StartOut(BaseModel):
    authorization_endpoint: str
    client_id: str
    scope: str
    redirect_uri: str


@router.post("/test-start")
def test_start(
    request: Request, session: SessionDep, settings: SettingsDep, user: SuperuserDep
) -> StartOut:
    """Where to send the browser for a Setup test (even while it is off)."""
    config = vives_login.config_from(settings, session)
    if config is None:
        raise vives_login.SetupError(
            "Fill in the Issuer URL, Client ID and Client secret first."
        )
    found = vives_login.start(request.app.state.oidc, config, settings)
    session.commit()
    return StartOut(**vars(found))


class TestIn(BaseModel):
    code: str
    code_verifier: str
    nonce: str


class TestOut(BaseModel):
    email: str | None
    name: str | None
    groups: list[str]
    programme: str | None
    year: str | None
    # The Role this login would get, or why it would be refused.
    role: str | None
    refusal: str | None


@router.post("/setup-test")
def setup_test(
    body: TestIn,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    user: SuperuserDep,
) -> TestOut:
    """Finish a Setup test: report what Authentik sent; no User is made."""
    report = vives_login.setup_test(
        session,
        request.app.state.oidc,
        settings,
        user,
        code=body.code,
        code_verifier=body.code_verifier,
        nonce=body.nonce,
    )
    return TestOut(**vars(report))


@router.post("/switch-on")
def switch_on(
    session: SessionDep, settings: SettingsDep, user: SuperuserDep
) -> ScreenOut:
    """From now on VIVES login only (after a Superuser Setup test)."""
    vives_login.switch_on(session, settings, user)
    return _screen(session, settings)
