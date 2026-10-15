"""Project Trello boards (spec #61): creating one Workspace and board per Project
and inviting its people."""

from contextlib import suppress
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from pmp_backend.domain import ProjectStatus
from pmp_backend.errors import Conflict
from pmp_backend.models import Project, TrelloGrant, User
from pmp_backend.services.projects import get_project
from pmp_backend.services.trello import ADMIN, LISTS, NORMAL, Trello, TrelloError
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
            invite_team(session, client, project)
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


def _wanted(project: Project) -> list[tuple[User, str]]:
    """Who belongs on the board: active Members as normal members, the Product
    Owner as admin."""
    wanted = [(member, NORMAL) for member in project.members if member.is_active]
    if project.product_owner.is_active:
        wanted.append((project.product_owner, ADMIN))
    return wanted


def invite_team(session: Session, client: Trello, project: Project) -> None:
    """Invite everyone who belongs on the board and was never invited, by their
    platform email, and remember which Trello member each became."""
    invited = set(
        session.scalars(
            select(TrelloGrant.user_id).where(TrelloGrant.project_id == project.id)
        )
    )
    for user, member_type in _wanted(project):
        if user.id in invited:
            continue
        member_id = client.invite(project.trello_board_id, user.email, member_type)
        if member_id is not None:
            session.add(
                TrelloGrant(
                    project_id=project.id,
                    trello_member_id=member_id,
                    user_id=user.id,
                    email=user.email,
                )
            )
            # Saved one by one, so a later failure keeps who was invited.
            session.commit()
