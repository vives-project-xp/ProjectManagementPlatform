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


class ProjectConflictError(ProjectError, Conflict):
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


def titles_owned_by(session: Session, user_id: int) -> list[str]:
    """Titles of all Projects (Active and Archived) this User is Product Owner of."""
    return list(
        session.scalars(
            select(Project.title)
            .where(Project.product_owner_id == user_id)
            .order_by(Project.title)
        )
    )


def titles_made_by(session: Session, student_id: int) -> list[str]:
    """Titles of the Projects whose Makers include this Student."""
    return list(
        session.scalars(
            select(Project.title)
            .where(Project.makers.contains([{"student_id": student_id}]))
            .order_by(Project.title)
        )
    )


def list_projects(
    session: Session, *, status: ProjectStatus | None = None
) -> list[Project]:
    query = select(Project).order_by(func.lower(Project.title))
    if status is not None:
        query = query.where(Project.status == status.value)
    return list(session.scalars(query))


def get_project(session: Session, project_id: int, *, lock: bool = False) -> Project:
    """The Project; with `lock`, its row stays locked until the next commit, so
    changes to its Members and Team size cannot interleave."""
    # Lock only the projects row ("FOR UPDATE OF projects"): the Product Owner is
    # joined in, and Postgres cannot lock the nullable side of that join.
    project = session.get(
        Project, project_id, with_for_update={"of": Project} if lock else None
    )
    if project is None:
        raise ProjectNotFoundError("This Project does not exist.")
    return project


def changeable_project(session: Session, project_id: int) -> Project:
    """The Project, locked until commit, refused when it is archived: Archived
    Projects are read-only (only restoring changes them)."""
    project = get_project(session, project_id, lock=True)
    if project.status == ProjectStatus.ARCHIVED.value:
        raise ProjectConflictError(
            f"{project.title} is archived, so it cannot be changed. Restore it first."
        )
    return project


def create_project(session: Session, fields: ProjectFields) -> Project:
    project = Project(status=ProjectStatus.ACTIVE.value)
    _apply(session, project, fields)
    session.add(project)
    _commit(session, fields.title)
    return project


def update_project(session: Session, project_id: int, fields: ProjectFields) -> Project:
    # Locked like adding a Member, so a lower maximum and a new Member can't
    # both pass their checks at the same moment.
    project = changeable_project(session, project_id)
    _apply(session, project, fields)
    _commit(session, fields.title)
    return project


def archive_project(session: Session, project_id: int) -> Project:
    """In one transaction: add the current Members to the Makers (never removing
    anyone, nobody twice), free those Students and make the Project read-only."""
    project = changeable_project(session, project_id)
    # Lock the Members' rows too (adding/moving a Student locks the Student's
    # row), so a Student moved away at this moment is neither recorded nor freed.
    members = list(
        session.scalars(
            select(User)
            .where(User.project_id == project.id)
            .order_by(User.last_name, User.first_name)
            .with_for_update()
        )
    )
    makers = list(project.makers)
    known = {maker["student_id"] for maker in makers}
    for member in members:
        if member.id not in known:
            makers.append(
                {
                    "student_id": member.id,
                    "name": member.full_name,
                    "programme": member.programme,
                    "year": member.year,
                }
            )
    # A new list (not an in-place change), so SQLAlchemy saves the JSONB column.
    project.makers = makers
    for member in members:
        member.project = None
    project.status = ProjectStatus.ARCHIVED.value
    session.commit()
    session.refresh(project)
    return project


def restore_project(session: Session, project_id: int) -> Project:
    """Active again, without Members; the Makers stay."""
    project = get_project(session, project_id, lock=True)
    if project.status != ProjectStatus.ARCHIVED.value:
        raise ProjectConflictError(f"{project.title} is not archived.")
    project.status = ProjectStatus.ACTIVE.value
    session.commit()
    return project


def _apply(session: Session, project: Project, fields: ProjectFields) -> None:
    if not 1 <= fields.team_size_min <= fields.team_size_max:
        raise ProjectError(
            "The Team size needs a minimum of at least 1 and a maximum "
            "of at least the minimum."
        )
    members = project.member_count if project.id is not None else 0
    if fields.team_size_max < members:
        raise ProjectConflictError(
            f"{project.title} has {members} Members, so the maximum Team size "
            f"cannot be lower than {members}. Remove Members first."
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
