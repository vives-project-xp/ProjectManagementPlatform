"""Create the starting accounts from logins.txt (one per Role).

Only on the first start, when there are no Users yet: a starting account that was
later edited or deleted never comes back.
"""

import logging
from pathlib import Path

from sqlalchemy.orm import Session

from pmp_backend.domain import Role, Year
from pmp_backend.services.programmes import first_programme_name
from pmp_backend.services.users import any_users, find_by_email, new_user

log = logging.getLogger(__name__)


def seed_starting_accounts(session: Session, logins_file: Path | None) -> None:
    if logins_file is None or not logins_file.is_file():
        log.warning("No logins file at %s; no starting accounts created.", logins_file)
        return
    # Never overwrite: a password changed by the User survives every deploy.
    if any_users(session):
        return

    seeded_roles: set[Role] = set()
    for line_number, line in enumerate(
        logins_file.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            role_text, email, password = (part.strip() for part in line.split(",", 2))
            role = Role(role_text)
        except ValueError:
            log.warning("Skipping invalid line %d in %s.", line_number, logins_file)
            continue

        # One starting account per Role and per email: the first line wins.
        if role in seeded_roles or find_by_email(session, email) is not None:
            continue
        seeded_roles.add(role)
        is_student = role is Role.STUDENT
        user = new_user(
            role=role,
            first_name=role.value.capitalize(),
            last_name="Account",
            email=email,
            temporary_password=password,
            programme=first_programme_name(session) if is_student else None,
            year=Year.FIRST if is_student else None,
        )
        session.add(user)
        log.info("Created starting account %s (%s).", user.email, role.value)
    session.commit()
