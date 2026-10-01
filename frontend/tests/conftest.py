import asyncio
import os
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
from nicegui import ui
from nicegui.testing import User

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


async def eventually(check: Callable[[], bool], retries: int = 60) -> None:
    """Wait until `check()` holds; pages reload their data asynchronously."""
    for _ in range(retries):
        if check():
            return
        await asyncio.sleep(0.05)
    assert check()


async def log_in(user: User, role: str, password: str | None = None) -> None:
    email, starting_password = STARTING_ACCOUNTS[role]
    await user.open("/login")
    user.find(marker="email").type(email)
    user.find(marker="password").type(password or starting_password)
    user.find(marker="log-in").click()


async def change_starting_password(user: User, role: str, new_password: str) -> None:
    _, starting_password = STARTING_ACCOUNTS[role]
    await user.should_see("Change your password")
    user.find(marker="current-password").type(starting_password)
    user.find(marker="new-password").type(new_password)
    user.find(marker="repeat-password").type(new_password)
    user.find(marker="change-password").click()


async def ready_to_work(user: User, role: str) -> None:
    """Log in as a starting account and get past the forced password change."""
    await log_in(user, role)
    await change_starting_password(user, role, f"{role}-own-password")
    # Navigation only appears once the Temporary password is gone; the home page
    # may need a moment to load its data.
    await user.should_see(marker="navigation", retries=30)


def project_titles(user: User) -> list[str]:
    table = user.find(marker="projects").elements.pop()
    assert isinstance(table, ui.table)
    return [row["title"] for row in table.rows]


def fill_project_form(user: User, title: str, minimum: int, maximum: int) -> None:
    title_input = user.find(marker="title").elements.pop()
    title_input.set_value(title)
    owner = user.find(marker="product-owner").elements.pop()
    assert isinstance(owner, ui.select)
    owner.set_value(
        next(key for key, name in owner.options.items() if name == "Teacher Account")
    )
    user.find(marker="team-size-min").elements.pop().set_value(minimum)
    user.find(marker="team-size-max").elements.pop().set_value(maximum)


async def create_project(
    user: User, title: str, minimum: int = 4, maximum: int = 6
) -> None:
    await user.open("/projects")
    await user.should_see(marker="projects")
    user.find(marker="new-project").click()
    fill_project_form(user, title, minimum, maximum)
    user.find(marker="create-project").click()
    await user.should_see(f"Project {title} was created.")
