"""Database helpers shared by the backend and frontend test suites."""

import os
from dataclasses import dataclass
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from pmp_backend.services.github import (
    CreatedRepo,
    GitHubAccount,
    GitHubUnavailableError,
    repo_exists_error,
)

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


@dataclass
class FakeRepo:
    id: int
    org: str
    name: str
    private: bool = False
    # Never given a first commit (spec #49: completely empty).
    empty: bool = True
    archived: bool = False

    @property
    def html_url(self) -> str:
        return f"https://github.com/{self.org}/{self.name}"


class FakeGitHub:
    """GitHub for tests: accounts in memory, no network. Set `failing` to make
    every call fail as if GitHub could not be reached."""

    def __init__(self) -> None:
        self.accounts: dict[str, GitHubAccount] = {}
        # By name, lower-cased (GitHub names are case-insensitive).
        self.repos: dict[str, FakeRepo] = {}
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

    def add_repo(self, org: str, name: str) -> FakeRepo:
        repo = FakeRepo(id=1000 + len(self.repos), org=org, name=name)
        self.repos[name.lower()] = repo
        return repo

    def create_org_repo(self, org: str, name: str) -> CreatedRepo:
        self._check()
        if name.lower() in self.repos:
            raise repo_exists_error(org, name)
        repo = self.add_repo(org, name)
        return CreatedRepo(id=repo.id, html_url=repo.html_url)
