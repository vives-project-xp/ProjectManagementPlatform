"""Project Trello boards (spec #61): creating one Workspace and board per Project
and keeping its people in line with the Project."""

from contextlib import suppress
from dataclasses import dataclass

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from pmp_backend.domain import ProjectStatus
from pmp_backend.errors import Conflict
from pmp_backend.models import Project, TrelloGrant, User
from pmp_backend.services.projects import get_project
from pmp_backend.services.trello import (
    ADMIN,
    LISTS,
    NORMAL,
    BoardInfo,
    Trello,
    TrelloError,
)
from pmp_backend.settings import Settings


class TrelloConflictError(TrelloError, Conflict):
    pass


@dataclass(frozen=True)
class BoardResult:
    project_id: int
    title: str
    created: bool
    message: str


def is_connected(settings: Settings) -> bool:
    return bool(settings.trello_api_key and settings.trello_token)


def check_connected(settings: Settings) -> None:
    if not is_connected(settings):
        raise TrelloConflictError("Trello isn't connected.")


def create_all(
    session: Session, client: Trello, settings: Settings
) -> list[BoardResult]:
    """Its own Workspace and private board, with the standard lists, for every
    Active Project with Members and no board yet; then its people are invited.
    One failing never stops the others."""
    check_connected(settings)
    candidates = list(
        session.scalars(
            select(Project.id)
            .where(
                Project.status == ProjectStatus.ACTIVE.value,
                Project.trello_board_id.is_(None),
            )
            .order_by(func.lower(Project.title))
        )
    )
    results = []
    for project_id in candidates:
        # Locked, so two Teachers pressing at once don't create it twice.
        project = get_project(session, project_id, lock=True)
        if project.trello_board_id is not None or not project.members:
            session.rollback()
            continue
        try:
            _create_board(client, project)
        except TrelloError as error:
            session.rollback()
            results.append(BoardResult(project.id, project.title, False, str(error)))
            continue
        session.commit()
        message = "Created"
        try:
            # Teams can start at once (spec #61, story 8).
            check_members(session, client, settings, project.id)
        except TrelloError as error:
            session.rollback()
            message = f"Created, but inviting failed: {error}"
        results.append(BoardResult(project.id, project.title, True, message))
    return results


def _create_board(client: Trello, project: Project) -> None:
    """The Workspace, its board and the lists; a half-made Workspace is removed
    again, so a retry starts clean."""
    workspace_id = client.create_workspace(project.title)
    try:
        board = client.create_board(workspace_id, project.title)
        for name in LISTS:
            client.add_list(board.id, name)
    except TrelloError:
        with suppress(TrelloError):
            client.delete_workspace(workspace_id)
        raise
    project.trello_workspace_id = workspace_id
    project.trello_board_id = board.id
    project.trello_board_url = board.url


def _wanted(project: Project) -> dict[int, tuple[User, str]]:
    """Who belongs on the board, by User id: active Members as normal members,
    the Product Owner as admin."""
    wanted = {
        member.id: (member, NORMAL) for member in project.members if member.is_active
    }
    owner = project.product_owner
    if owner.is_active:
        wanted[owner.id] = (owner, ADMIN)
    return wanted


class BoardGoneError(TrelloConflictError):
    def __init__(self) -> None:
        super().__init__(
            "The Trello board no longer exists. Check members to forget it."
        )


def _board(client: Trello, project: Project) -> BoardInfo:
    if project.trello_board_id is None:
        raise TrelloConflictError(f"{project.title} has no Trello board yet.")
    info = client.board(project.trello_board_id)
    if info is None:
        raise BoardGoneError()
    return info


@dataclass
class CheckResult:
    invited: list[str]
    removed: list[str]
    updated: list[str]
    renamed: bool = False
    board_gone: bool = False

    @property
    def message(self) -> str:
        if self.board_gone:
            return "The Trello board no longer exists."
        parts = [
            f"{verb} {', '.join(names)}."
            for verb, names in (
                ("Invited", self.invited),
                ("Changed the role of", self.updated),
                ("Removed", self.removed),
            )
            if names
        ]
        if self.renamed:
            parts.append("Renamed the board.")
        return " ".join(parts) or "Everything was already in order."


def check_members(
    session: Session, client: Trello, settings: Settings, project_id: int
) -> CheckResult:
    """Bring the board in line with the Project: invite who is missing by their
    platform email, fix membership types, remove the members the platform added
    who no longer belong, and give the board the Project's title. Members the
    platform didn't add, and the owner account, are never touched."""
    check_connected(settings)
    project = get_project(session, project_id, lock=True)
    try:
        info = _board(client, project)
    except BoardGoneError:
        project.trello_workspace_id = None
        project.trello_board_id = None
        project.trello_board_url = None
        session.execute(delete(TrelloGrant).where(TrelloGrant.project_id == project.id))
        session.commit()
        return CheckResult([], [], [], board_gone=True)
    try:
        result = _check(session, client, project, info)
    except TrelloError:
        # Keep what already happened on Trello, so nobody is lost track of.
        session.commit()
        raise
    session.commit()
    return result


def _check(
    session: Session, client: Trello, project: Project, info: BoardInfo
) -> CheckResult:
    board_id = project.trello_board_id
    result = CheckResult([], [], [])
    if info.name != project.title:
        client.rename(project.trello_workspace_id, board_id, project.title)
        result.renamed = True
    wanted = _wanted(project)
    on_board = {m.member_id: m for m in client.memberships(board_id)}
    grants = list(
        session.scalars(select(TrelloGrant).where(TrelloGrant.project_id == project.id))
    )
    granted: dict[int, TrelloGrant] = {}
    for grant in grants:
        user = session.get(User, grant.user_id) if grant.user_id else None
        if grant.trello_member_id not in on_board:
            # Removed in Trello by hand: forget it, and invite again if wanted.
            session.delete(grant)
        elif user is None or user.id not in wanted or grant.email != user.email:
            # Left the Project, deactivated, deleted, or their email changed.
            client.remove_member(board_id, grant.trello_member_id)
            session.delete(grant)
            result.removed.append(user.full_name if user else grant.email)
        else:
            granted[user.id] = grant
    session.flush()

    for user_id, (user, member_type) in wanted.items():
        grant = granted.get(user_id)
        if grant is None:
            member_id = client.invite(board_id, user.email, member_type)
            if member_id is not None:
                session.add(
                    TrelloGrant(
                        project_id=project.id,
                        trello_member_id=member_id,
                        user_id=user.id,
                        email=user.email,
                    )
                )
                session.flush()
                result.invited.append(user.full_name)
        elif on_board[grant.trello_member_id].member_type != member_type:
            client.set_member_type(board_id, grant.trello_member_id, member_type)
            result.updated.append(user.full_name)
    return result


def check_all(
    session: Session, client: Trello, settings: Settings
) -> list[tuple[Project, str]]:
    """Check the members of every Active Project's board."""
    check_connected(settings)
    ids = list(
        session.scalars(
            select(Project.id)
            .where(
                Project.status == ProjectStatus.ACTIVE.value,
                Project.trello_board_id.is_not(None),
            )
            .order_by(func.lower(Project.title))
        )
    )
    results = []
    for project_id in ids:
        try:
            message = check_members(session, client, settings, project_id).message
        except TrelloError as error:
            session.rollback()
            message = f"Failed. {error}"
        results.append((get_project(session, project_id), message))
    return results


# Statuses: "has_access", "invited" (no Trello account with that email yet) or
# "not_invited".


def _statuses(session: Session, client: Trello, project: Project) -> dict[int, str]:
    """Each User the platform invited to the board, by id, and their status."""
    on_board = {m.member_id: m for m in client.memberships(project.trello_board_id)}
    statuses = {}
    for grant in session.scalars(
        select(TrelloGrant).where(TrelloGrant.project_id == project.id)
    ):
        member = on_board.get(grant.trello_member_id)
        if grant.user_id is not None and member is not None:
            statuses[grant.user_id] = "invited" if member.unconfirmed else "has_access"
    return statuses


@dataclass(frozen=True)
class PersonAccess:
    name: str
    role: str
    email: str
    status: str


def people_access(
    session: Session, client: Trello, settings: Settings, project_id: int
) -> tuple[str, list[PersonAccess]]:
    """The board URL and, for the Product Owner and each Member, their status,
    read live from Trello."""
    check_connected(settings)
    project = get_project(session, project_id)
    info = _board(client, project)
    statuses = _statuses(session, client, project)

    def access(user: User, role: str) -> PersonAccess:
        status = statuses.get(user.id, "not_invited")
        return PersonAccess(user.full_name, role, user.email, status)

    people = [access(project.product_owner, "Product Owner")]
    people += [access(member, "Member") for member in project.members]
    return info.url, people


@dataclass(frozen=True)
class StudentAccess:
    board_url: str | None
    # "no_board", "not_invited", "invited" or "has_access".
    status: str
    email: str


def student_access(
    session: Session, client: Trello, settings: Settings, student: User
) -> StudentAccess:
    """A Student's Trello board and their next step to get access."""
    project = student.project
    if project is None or project.trello_board_id is None or not is_connected(settings):
        return StudentAccess(None, "no_board", student.email)
    info = _board(client, project)
    status = _statuses(session, client, project).get(student.id, "not_invited")
    return StudentAccess(info.url, status, student.email)


# Following the Project (spec #61): a warning to show when Trello refused, never
# an error, so Trello problems never block the platform.


def follow_status(client: Trello, settings: Settings, project: Project) -> str | None:
    """Close the board of an Archived Project, reopen it for an Active one."""
    if project.trello_board_id is None or not is_connected(settings):
        return None
    archived = project.status == ProjectStatus.ARCHIVED.value
    try:
        client.set_closed(project.trello_board_id, archived)
    except TrelloError as error:
        verb, action = ("archived", "closed") if archived else ("restored", "reopened")
        return (
            f"{project.title} was {verb}, but its Trello board could not be "
            f"{action}: {error}"
        )
    return None


def follow_title(client: Trello, settings: Settings, project: Project) -> str | None:
    """Give the board and its Workspace the Project's (new) title."""
    if project.trello_board_id is None or not is_connected(settings):
        return None
    try:
        client.rename(
            project.trello_workspace_id, project.trello_board_id, project.title
        )
    except TrelloError as error:
        return (
            f"Saved, but the Trello board couldn't be renamed: {error} "
            "Check members renames it later."
        )
    return None
