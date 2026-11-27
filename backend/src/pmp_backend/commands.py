"""Commands for someone with access to the VM (spec #160, #163), run in the
backend container:

    docker exec pmp-backend-1 pmp-break-glass [email]
    docker exec pmp-backend-1 pmp-vives-login-off

The only ways around VIVES login once it is on (ADR 0011)."""

import logging
import sys

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pmp_backend.services import break_glass as service
from pmp_backend.settings import Settings

log = logging.getLogger("pmp_backend.commands")


def _session():
    settings = Settings()
    engine = create_engine(settings.database_url)
    return settings, sessionmaker(bind=engine)()


def break_glass() -> None:
    """Print a one-time login link for a Superuser (15 minutes, once)."""
    logging.basicConfig(level=logging.INFO)
    email = sys.argv[1] if len(sys.argv) > 1 else None
    settings, session = _session()
    with session:
        try:
            user, code = service.create(session, email)
        except service.BreakGlassError as error:
            print(f"Refused: {error}", file=sys.stderr)
            raise SystemExit(1) from error
    print(f"One-time login link for {user.full_name} ({user.email}),")
    print(f"valid for {service.LIFETIME_MINUTES} minutes and usable once:")
    print(f"{settings.site_url.rstrip('/')}/auth/break-glass?code={code}")


def vives_login_off() -> None:
    """Switch VIVES login off: password login is back as before."""
    logging.basicConfig(level=logging.INFO)
    _, session = _session()
    with session:
        if service.switch_off(session):
            print("VIVES login is off: the site has password login again.")
        else:
            print("VIVES login was not on.")
