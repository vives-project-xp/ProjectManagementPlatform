"""Test login: log in as any active User without a password, so the team can try
every Role quickly. Only mounted when the `dev_login` setting is on; never turn
it on once real Students and Teachers use the site."""

import logging

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from pmp_backend.api.auth import LoginOut, login_out
from pmp_backend.api.deps import SessionDep, SettingsDep
from pmp_backend.domain import Role
from pmp_backend.errors import NotFound
from pmp_backend.models import User
from pmp_backend.services import vives_login

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/dev-login", tags=["dev-login"])

ROLE_ORDER = [Role.SUPERUSER.value, Role.TEACHER.value, Role.STUDENT.value]


class DevLoginUserOut(BaseModel):
    id: int
    name: str
    role: str


class DevLoginIn(BaseModel):
    user_id: int


def _not_with_vives_login(session) -> None:
    """The Test login never works once VIVES login is on (#163)."""
    if vives_login.is_on(session):
        log.warning("DEV_LOGIN is set but ignored: VIVES login is on")
        raise NotFound("There is no Test login.")


@router.get("/users")
def users(session: SessionDep) -> list[DevLoginUserOut]:
    """Active Users, by Role (Superuser, Teachers, Students), then by name."""
    _not_with_vives_login(session)
    found = session.scalars(
        select(User).where(User.is_active).order_by(User.last_name, User.first_name)
    )
    ordered = sorted(found, key=lambda user: ROLE_ORDER.index(user.role))
    return [
        DevLoginUserOut(id=user.id, name=user.full_name, role=user.role)
        for user in ordered
    ]


@router.post("")
def log_in_as(body: DevLoginIn, session: SessionDep, settings: SettingsDep) -> LoginOut:
    _not_with_vives_login(session)
    user = session.get(User, body.user_id)
    if user is None or not user.is_active:
        raise NotFound("This User does not exist or is deactivated.")
    return login_out(user, settings)
