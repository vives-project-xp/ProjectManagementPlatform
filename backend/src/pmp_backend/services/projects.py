"""Creating and editing Projects (spec #3, project service)."""

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from pmp_backend.domain import ProjectStatus, Role
from pmp_backend.errors import Conflict, NotFound, Refused
from pmp_backend.models import Project, User


class ProjectError(Refused):
    """A Project could not be saved as asked; the message is fit to show."""


class DuplicateTitleError(ProjectError, Conflict):
    pass


class ProjectNotFoundError(ProjectError, NotFound):
    pass


@dataclass(frozen=True)
class ProjectFields:
    """What a Teacher fills in when creating or editing a Project."""

    title: str
    description: str | None
    product_owner_id: int
    team_size_min: int
    team_size_max: int


def active_teachers(session: Session) -> list[User]:
    """The Users who can be Product Owner."""
    return list(
        session.scalars(
            select(User)
            .where(User.role == Role.TEACHER.value, User.is_active)
            .order_by(User.last_name, User.first_name)
        )
    )


def active_titles_owned_by(session: Session, user_id: int) -> list[str]:
    """Titles of the active Projects this User is Product Owner of."""
    return list(
        session.scalars(
            select(Project.title)
            .where(
                Project.product_owner_id == user_id,
                Project.status == ProjectStatus.ACTIVE.value,
            )
            .order_by(Project.title)
        )
    )


def list_projects(session: Session) -> list[Project]:
    return list(session.scalars(select(Project).order_by(func.lower(Project.title))))


def get_project(session: Session, project_id: int) -> Project:
    project = session.get(Project, project_id)
    if project is None:
        raise ProjectNotFoundError("This Project does not exist.")
    return project


def create_project(session: Session, fields: ProjectFields) -> Project:
    project = Project(status=ProjectStatus.ACTIVE.value)
    _apply(session, project, fields)
    session.add(project)
    _commit(session, fields.title)
    return project


def update_project(session: Session, project_id: int, fields: ProjectFields) -> Project:
    project = get_project(session, project_id)
    _apply(session, project, fields)
    _commit(session, fields.title)
    return project


def _apply(session: Session, project: Project, fields: ProjectFields) -> None:
    if not 1 <= fields.team_size_min <= fields.team_size_max:
        raise ProjectError(
            "The Team size needs a minimum of at least 1 and a maximum "
            "of at least the minimum."
        )
    owner = session.get(User, fields.product_owner_id)
    if owner is None or owner.role != Role.TEACHER.value or not owner.is_active:
        raise ProjectError("The Product Owner must be an active Teacher.")
    same_title = select(Project).where(
        func.lower(Project.title) == fields.title.lower()
    )
    if project.id is not None:
        # Keeping (or re-casing) a Project's own title is not a duplicate.
        same_title = same_title.where(Project.id != project.id)
    taken = session.scalar(same_title)
    if taken is not None:
        raise DuplicateTitleError(
            f"A Project called {taken.title} already exists (Archived Projects "
            "included)."
        )
    project.title = fields.title
    project.description = fields.description or None
    project.product_owner = owner
    project.team_size_min = fields.team_size_min
    project.team_size_max = fields.team_size_max


def _commit(session: Session, title: str) -> None:
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        if "uq_projects_title_lower" not in str(error.orig):
            raise
        # Someone else took the title between the check and the save.
        raise DuplicateTitleError(
            f"A Project called {title} already exists."
        ) from error
