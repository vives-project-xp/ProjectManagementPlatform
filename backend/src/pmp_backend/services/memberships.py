"""Adding, moving and removing Members (spec #3, membership service).

A Student is a Member of at most one Project (`users.project_id`). Deactivated
Students stay Members and count towards the Team size.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from pmp_backend.domain import ProjectStatus, Role
from pmp_backend.errors import Conflict, NotFound, Refused
from pmp_backend.models import Project, User
from pmp_backend.services.projects import get_project


class MembershipError(Refused):
    pass


class MembershipConflictError(MembershipError, Conflict):
    pass


class MoveConfirmationNeededError(MembershipConflictError):
    code = "move_confirmation_needed"


class NotAMemberError(MembershipError, NotFound):
    pass


def member_count(session: Session, project_id: int) -> int:
    return session.scalar(
        select(func.count(User.id)).where(User.project_id == project_id)
    )


def _name(user: User) -> str:
    return f"{user.first_name} {user.last_name}"


def _locked_project(session: Session, project_id: int) -> Project:
    """The Project, locked until commit so two adds cannot both take the last place."""
    project = get_project(session, project_id)
    session.execute(
        select(Project.id).where(Project.id == project_id).with_for_update()
    )
    if project.status != ProjectStatus.ACTIVE.value:
        raise MembershipConflictError(
            f"{project.title} is archived; its Members cannot change."
        )
    return project


def add_member(
    session: Session, project_id: int, student_id: int, *, confirm_move: bool = False
) -> Project:
    """Make a Student a Member; moving them from another Project needs confirmation."""
    project = _locked_project(session, project_id)
    student = session.get(User, student_id)
    if student is None or student.role != Role.STUDENT.value:
        raise MembershipError("Only Students can be Members.")
    if not student.is_active:
        raise MembershipError(
            f"{_name(student)} is a Deactivated Student and cannot be added as a "
            "new Member."
        )
    if student.project_id == project.id:
        raise MembershipConflictError(
            f"{_name(student)} is already a Member of {project.title}."
        )
    count = member_count(session, project.id)
    if count >= project.team_size_max:
        raise MembershipConflictError(
            f"{project.title} is full ({count} / {project.team_size_min}–"
            f"{project.team_size_max}). Raise the maximum Team size first."
        )
    if student.project is not None and not confirm_move:
        raise MoveConfirmationNeededError(
            f"{_name(student)} is a Member of {student.project.title}. "
            f"Move {_name(student)} to {project.title}?"
        )
    # One update: leaving the old Project and joining this one happen together.
    student.project = project
    session.commit()
    session.refresh(project)
    return project


def remove_member(session: Session, project_id: int, student_id: int) -> Project:
    project = _locked_project(session, project_id)
    student = session.get(User, student_id)
    if student is None or student.project_id != project.id:
        raise NotAMemberError(f"This Student is not a Member of {project.title}.")
    student.project = None
    session.commit()
    session.refresh(project)
    return project
