import os
from pathlib import Path

import httpx
import pytest

from pmp_backend import testing
from pmp_backend.app import create_app
from pmp_backend.services.seeding import seed_starting_accounts
from pmp_backend.settings import Settings
from pmp_frontend import api

pytest_plugins = ["nicegui.testing.user_plugin"]

# Read by main.py, which the user fixture runs for every test.
os.environ.setdefault("STORAGE_SECRET", "test-storage-secret")

STARTING_ACCOUNTS = {
    "superuser": ("superuser@pmp.local", "super-secret-1"),
    "teacher": ("teacher@pmp.local", "teacher-secret-1"),
    "student": ("student@pmp.local", "student-secret-1"),
}


@pytest.fixture(scope="session", autouse=True)
def _migrated_database() -> None:
    testing.migrate(testing.TEST_DATABASE_URL)


@pytest.fixture(autouse=True)
def backend_in_process(tmp_path: Path):
    """Route the frontend's API calls to the real backend app, in this process."""
    testing.reset(testing.TEST_DATABASE_URL)
    logins_file = tmp_path / "logins.txt"
    logins_file.write_text(
        "".join(
            f"{role},{email},{pw}\n" for role, (email, pw) in STARTING_ACCOUNTS.items()
        ),
        encoding="utf-8",
    )
    backend = create_app(
        Settings(
            database_url=testing.TEST_DATABASE_URL,
            jwt_secret="test-secret-that-is-long-enough-for-hs256-signing",
            logins_file=logins_file,
        )
    )
    # ASGITransport does not run the backend's startup, so seed here.
    with backend.state.sessionmaker() as session:
        seed_starting_accounts(session, logins_file)
    api.use_transport(httpx.ASGITransport(app=backend))
    yield
    api.use_transport(None)
