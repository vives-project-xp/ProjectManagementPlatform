"""Database helpers shared by the backend and frontend test suites."""

import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from pmp_backend.services.github import GitHubAccount, GitHubUnavailableError

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://pmp:pmp@localhost:5433/pmp_test",
)

_ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


def migrate(database_url: str = TEST_DATABASE_URL) -> None:
    """Bring the test database to the latest migration."""
    os.environ["DATABASE_URL"] = database_url
    command.upgrade(Config(str(_ALEMBIC_INI)), "head")


def reset(database_url: str = TEST_DATABASE_URL) -> None:
    """Empty every table so each test starts from a clean database."""
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE projects, users, programmes, top3_round "
                "RESTART IDENTITY CASCADE"
            )
        )
        # As migration 0004 leaves the list.
        connection.execute(
            text("INSERT INTO programmes (name) VALUES ('Electronics-ICT')")
        )
    engine.dispose()


class FakeGitHub:
    """GitHub for tests: accounts in memory, no network. Set `failing` to make
    every call fail as if GitHub could not be reached."""

    def __init__(self) -> None:
        self.accounts: dict[str, GitHubAccount] = {}
        self.failing = False

    def add_account(self, login: str, name: str | None = None) -> None:
        self.accounts[login.lower()] = GitHubAccount(
            login=login, name=name, avatar_url=f"https://avatars.example/{login}.png"
        )

    def _check(self) -> None:
        if self.failing:
            raise GitHubUnavailableError()

    def user(self, username: str) -> GitHubAccount | None:
        self._check()
        return self.accounts.get(username.lower())
