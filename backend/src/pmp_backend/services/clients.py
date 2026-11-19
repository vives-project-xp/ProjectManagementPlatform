"""Clients following Projects (spec #132, #134): staff link and unlink them
and give one of a Project's Clients the Client Product Owner label; a Client
sees the Projects they follow read-only."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from pmp_backend.domain import ProjectStatus, Role
from pmp_backend.errors import Conflict, NotFound, Refused
from pmp_backend.models import Project, ProjectClient, User
from pmp_backend.services.projects import changeable_project

NOT_FOLLOWED = "You don't follow this Project."


class ClientError(Refused):
    """Linking a Client refused; the message says why."""


class ClientConflictError(ClientError, Conflict):
    pass


class ClientNotFoundError(ClientError, NotFound):
    pass


def active_clients(session: Session) -> list[User]:
    """Every active Client, by name, to choose from."""
    return list(
        session.scalars(
            select(User)
            .where(User.role == Role.CLIENT.value, User.is_active.is_(True))
            .order_by(User.last_name, User.first_name)
        )
    )


def _link(project: Project, client_id: int) -> ProjectClient | None:
    return next(
        (link for link in project.client_links if link.client_id == client_id), None
    )


def add_client(session: Session, project_id: int, client_id: int) -> Project:
    """Let an active Client follow an Active Project."""
    project = changeable_project(session, project_id)
    client = session.get(User, client_id)
    if client is None or client.role != Role.CLIENT.value:
        raise ClientNotFoundError("This Client doesn't exist.")
    if not client.is_active:
        raise ClientError(f"{client.full_name} is deactivated.")
    if _link(project, client_id) is not None:
        raise ClientConflictError(f"{client.full_name} already follows this Project.")
    session.add(ProjectClient(project_id=project.id, client_id=client.id))
    session.commit()
    session.refresh(project)
    return project


def remove_client(session: Session, project_id: int, client_id: int) -> Project:
    """Stop a Client following an Active Project (the label goes with them)."""
    project = changeable_project(session, project_id)
    link = _link(project, client_id)
    if link is None:
        raise ClientNotFoundError("This Client doesn't follow this Project.")
    session.delete(link)
    session.commit()
    session.refresh(project)
    return project


def set_client_product_owner(
    session: Session, project_id: int, client_id: int | None
) -> Project:
    """Give one of the Project's Clients the Client Product Owner label (a
    label only), or take it away with None."""
    project = changeable_project(session, project_id)
    if client_id is not None and _link(project, client_id) is None:
        raise ClientNotFoundError("This Client doesn't follow this Project.")
    for link in project.client_links:
        link.is_client_product_owner = False
    session.flush()
    if client_id is not None:
        _link(project, client_id).is_client_product_owner = True
    session.commit()
    session.refresh(project)
    return project


def followed_projects(session: Session, client: User) -> list[Project]:
    """The Projects a Client follows, Active ones first, then by title."""
    found = session.scalars(
        select(Project)
        .join(ProjectClient, ProjectClient.project_id == Project.id)
        .where(ProjectClient.client_id == client.id)
        .order_by(Project.status, Project.title)
    )
    return list(found)


def followed_project(session: Session, client: User, project_id: int) -> Project:
    """A Project the Client follows; NotFound otherwise (never says whether
    the Project exists)."""
    project = session.get(Project, project_id)
    if project is None or _link(project, client.id) is None:
        raise ClientNotFoundError(NOT_FOLLOWED)
    return project


def follows(session: Session, client: User, project_id: int) -> bool:
    return (
        session.get(ProjectClient, {"project_id": project_id, "client_id": client.id})
        is not None
    )


def is_archived(project: Project) -> bool:
    return project.status == ProjectStatus.ARCHIVED.value
