"""Database helpers shared by the backend and frontend test suites."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from pmp_backend.services.github import (
    Collaborator,
    CreatedRepo,
    GitHubAccount,
    GitHubUnavailableError,
    Invitation,
    RepoInfo,
    repo_exists_error,
)
from pmp_backend.services.trello import (
    BoardInfo,
    CreatedBoard,
    Membership,
    TrelloError,
    TrelloUnavailableError,
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
                "TRUNCATE projects, users, programmes, top3_round, deadlines "
                "RESTART IDENTITY CASCADE"
            )
        )
        # As migration 0004 leaves the list.
        connection.execute(
            text("INSERT INTO programmes (name) VALUES ('Electronics-ICT')")
        )
    engine.dispose()


@dataclass
class FakeInvitation:
    id: int
    login: str
    permission: str
    expired: bool = False


@dataclass
class FakeRepo:
    id: int
    org: str
    name: str
    private: bool = False
    # Never given a first commit (spec #49: completely empty).
    empty: bool = True
    archived: bool = False
    # By login, lower-cased: (login, "write" or "admin").
    collaborators: dict[str, tuple[str, str]] = field(default_factory=dict)
    invitations: dict[str, FakeInvitation] = field(default_factory=dict)

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
        self._invitation_ids = 0

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

    def _by_full_name(self, full_name: str) -> FakeRepo:
        return self.repos[full_name.split("/")[1].lower()]

    def repo(self, repo_id: int) -> RepoInfo | None:
        self._check()
        for repo in self.repos.values():
            if repo.id == repo_id:
                return RepoInfo(f"{repo.org}/{repo.name}", repo.html_url)
        return None

    def collaborators(self, full_name: str) -> list[Collaborator]:
        self._check()
        people = self._by_full_name(full_name).collaborators.values()
        return [Collaborator(login, permission) for login, permission in people]

    def invitations(self, full_name: str) -> list[Invitation]:
        self._check()
        return [
            Invitation(inv.id, inv.login, inv.permission, inv.expired)
            for inv in self._by_full_name(full_name).invitations.values()
        ]

    def invite(self, full_name: str, login: str, permission: str) -> None:
        self._check()
        repo = self._by_full_name(full_name)
        key = login.lower()
        if key in repo.collaborators:
            repo.collaborators[key] = (repo.collaborators[key][0], permission)
            return
        self._invitation_ids += 1
        repo.invitations[key] = FakeInvitation(self._invitation_ids, login, permission)

    def remove_collaborator(self, full_name: str, login: str) -> None:
        self._check()
        del self._by_full_name(full_name).collaborators[login.lower()]

    def delete_invitation(self, full_name: str, invitation_id: int) -> None:
        self._check()
        invitations = self._by_full_name(full_name).invitations
        key = next(k for k, inv in invitations.items() if inv.id == invitation_id)
        del invitations[key]

    # What people do on GitHub, for tests.

    def accept(self, repo_name: str, login: str) -> None:
        repo = self.repos[repo_name.lower()]
        invitation = repo.invitations.pop(login.lower())
        repo.collaborators[login.lower()] = (invitation.login, invitation.permission)

    def expire(self, repo_name: str, login: str) -> None:
        self.repos[repo_name.lower()].invitations[login.lower()].expired = True

    def set_archived(self, full_name: str, archived: bool) -> None:
        self._check()
        self._by_full_name(full_name).archived = archived


@dataclass
class FakeMember:
    member_id: str
    # None for the owner account (Trello never shows emails anyway).
    email: str | None
    member_type: str
    unconfirmed: bool = False


@dataclass
class FakeBoard:
    id: str
    workspace_id: str
    name: str
    private: bool
    lists: list[str] = field(default_factory=list)
    closed: bool = False
    # By member id; the owner account is on every board as admin.
    members: dict[str, FakeMember] = field(default_factory=dict)

    @property
    def url(self) -> str:
        return f"https://trello.com/b/{self.id}"

    def emails(self) -> dict[str, str]:
        """Each invited email and its membership type."""
        return {
            m.email: m.member_type for m in self.members.values() if m.email is not None
        }


OWNER_ID = "owner"


class FakeTrello:
    """Trello for tests: Workspaces and boards in memory, no network. Emails in
    `accounts` have a Trello account (they join at once); others stay
    unconfirmed. Set `failing` to make every call fail as if Trello could not be
    reached, or put a name in `refused_names` to refuse that board."""

    def __init__(self) -> None:
        # By id: the Workspace's display name.
        self.workspaces: dict[str, str] = {}
        self.boards: dict[str, FakeBoard] = {}
        self.accounts: set[str] = set()
        self.failing = False
        self.refused_names: set[str] = set()
        self._ids = 0

    def _check(self) -> None:
        if self.failing:
            raise TrelloUnavailableError()

    def _next_id(self, prefix: str) -> str:
        self._ids += 1
        return f"{prefix}{self._ids}"

    def board_named(self, name: str) -> FakeBoard:
        return next(b for b in self.boards.values() if b.name == name)

    def create_workspace(self, name: str) -> str:
        self._check()
        workspace_id = self._next_id("w")
        self.workspaces[workspace_id] = name
        return workspace_id

    def delete_workspace(self, workspace_id: str) -> None:
        self._check()
        del self.workspaces[workspace_id]
        for board_id in [
            b.id for b in self.boards.values() if b.workspace_id == workspace_id
        ]:
            del self.boards[board_id]

    def create_board(self, workspace_id: str, name: str) -> CreatedBoard:
        self._check()
        if name in self.refused_names:
            raise TrelloError("Trello refused: the board limit was reached")
        board = FakeBoard(self._next_id("b"), workspace_id, name, private=True)
        board.members[OWNER_ID] = FakeMember(OWNER_ID, None, "admin")
        self.boards[board.id] = board
        return CreatedBoard(id=board.id, url=board.url)

    def add_list(self, board_id: str, name: str) -> None:
        self._check()
        self.boards[board_id].lists.append(name)

    def memberships(self, board_id: str) -> list[Membership]:
        self._check()
        return [
            Membership(m.member_id, m.member_type, m.unconfirmed)
            for m in self.boards[board_id].members.values()
        ]

    def invite(self, board_id: str, email: str, member_type: str) -> str | None:
        self._check()
        board = self.boards[board_id]
        if email in board.emails():
            return None
        member = FakeMember(
            self._next_id("m"), email, member_type, email not in self.accounts
        )
        board.members[member.member_id] = member
        return member.member_id

    def board(self, board_id: str) -> BoardInfo | None:
        self._check()
        board = self.boards.get(board_id)
        return None if board is None else BoardInfo(board.name, board.url)

    def rename(self, workspace_id: str, board_id: str, name: str) -> None:
        self._check()
        self.workspaces[workspace_id] = name
        self.boards[board_id].name = name

    def set_closed(self, board_id: str, closed: bool) -> None:
        self._check()
        self.boards[board_id].closed = closed

    def set_member_type(self, board_id: str, member_id: str, member_type: str) -> None:
        self._check()
        self.boards[board_id].members[member_id].member_type = member_type

    def remove_member(self, board_id: str, member_id: str) -> None:
        self._check()
        del self.boards[board_id].members[member_id]

    # What people do on Trello, for tests.

    def sign_up(self, email: str) -> None:
        """The person makes a Trello account with this email: their invitations
        are confirmed."""
        self.accounts.add(email)
        for board in self.boards.values():
            for member in board.members.values():
                if member.email == email:
                    member.unconfirmed = False
