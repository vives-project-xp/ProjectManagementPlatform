"""The Break-glass link (spec #160, #163, ADR 0011): when Authentik fails,
someone with VM access prints a one-time login link for a Superuser. Only a
hash of the code is kept; it works once, for 15 minutes, and every use is
logged. Also switching VIVES login off, only from the VM."""

import hashlib
import logging
import secrets
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from pmp_backend.domain import Role
from pmp_backend.errors import Forbidden
from pmp_backend.models import BreakGlassCode, User
from pmp_backend.services import vives_login

log = logging.getLogger(__name__)

LIFETIME_MINUTES = 15
WRONG = "This login link is wrong, used or expired."


class BreakGlassError(Forbidden):
    """No link could be made, or a link was refused."""


def _hash(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def create(session: Session, email: str | None) -> tuple[User, str]:
    """A fresh code for that Superuser (or the only active one)."""
    query = select(User).where(User.role == Role.SUPERUSER.value, User.is_active)
    if email:
        query = query.where(User.email == email.strip().lower())
    found = session.scalars(query).all()
    if not found:
        raise BreakGlassError("No active Superuser with that email.")
    if len(found) > 1:
        raise BreakGlassError(
            "There are several Superusers: give the email of the one to log in as."
        )
    user = found[0]
    code = secrets.token_urlsafe(32)
    now = session.scalar(select(func.now()))
    session.add(
        BreakGlassCode(
            code_hash=_hash(code),
            user_id=user.id,
            expires_at=now + timedelta(minutes=LIFETIME_MINUTES),
        )
    )
    session.commit()
    log.warning("A Break-glass link was made for User %s", user.id)
    return user, code


def use(session: Session, code: str) -> User:
    """The Superuser behind a valid, unused code; it can't be used again."""
    row = session.scalar(
        select(BreakGlassCode)
        .where(BreakGlassCode.code_hash == _hash(code))
        .with_for_update()
    )
    now = session.scalar(select(func.now()))
    if row is None or row.used_at is not None or row.expires_at <= now:
        log.warning("A wrong, used or expired Break-glass link was tried")
        session.rollback()
        raise BreakGlassError(WRONG)
    user = session.get(User, row.user_id)
    if user is None or not user.is_active or user.role != Role.SUPERUSER.value:
        session.rollback()
        raise BreakGlassError(WRONG)
    row.used_at = now
    session.commit()
    log.warning("User %s logged in with a Break-glass link", user.id)
    return user


def switch_off(session: Session) -> bool:
    """VIVES login off; whether it was on."""
    row = vives_login.locked_row(session)
    if row is None or row.enabled_at is None:
        session.rollback()
        return False
    row.enabled_at = row.enabled_by_id = None
    row.tested_fingerprint = None
    session.commit()
    log.warning("VIVES login was switched off on the server")
    return True
