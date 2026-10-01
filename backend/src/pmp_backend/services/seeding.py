"""Create the starting accounts from logins.txt (one per Role) if they don't exist."""

import logging
from pathlib import Path

from sqlalchemy.orm import Session

from pmp_backend.domain import Programme, Role, Year
from pmp_backend.models import User
from pmp_backend.security import hash_password
from pmp_backend.services.users import find_by_email, normalize_email

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

        email = normalize_email(email)
        # Never overwrite: a password changed by the User survives every deploy.
        if find_by_email(session, email) is not None:
            continue
        is_student = role is Role.STUDENT
        session.add(
            User(
                first_name=role.value.capitalize(),
                last_name="Account",
                email=email,
                password_hash=hash_password(password),
                role=role.value,
                must_change_password=True,
                programme=Programme.ELECTRONICS_ICT.value if is_student else None,
                year=Year.FIRST.value if is_student else None,
            )
        )
        log.info("Created starting account %s (%s).", email, role.value)
    session.commit()
