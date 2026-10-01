"""Create the starting accounts from logins.txt (one per Role) if they don't exist."""

import logging
from pathlib import Path

from sqlalchemy.orm import Session

from pmp_backend.domain import Programme, Role, Year
from pmp_backend.services.users import find_by_email, new_user

log = logging.getLogger(__name__)


def seed_starting_accounts(session: Session, logins_file: Path | None) -> None:
    if logins_file is None or not logins_file.is_file():
        log.warning("No logins file at %s; no starting accounts created.", logins_file)
        return

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

        # Never overwrite: a password changed by the User survives every deploy.
        if find_by_email(session, email) is not None:
            continue
        is_student = role is Role.STUDENT
        user = new_user(
            role=role,
            first_name=role.value.capitalize(),
            last_name="Account",
            email=email,
            temporary_password=password,
            programme=Programme.ELECTRONICS_ICT if is_student else None,
            year=Year.FIRST if is_student else None,
        )
        session.add(user)
        log.info("Created starting account %s (%s).", user.email, role.value)
    session.commit()
