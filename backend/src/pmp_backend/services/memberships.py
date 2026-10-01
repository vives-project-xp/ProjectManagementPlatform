"""Adding, moving and removing Members (spec #3, membership service).

A Student is a Member of at most one Project (`users.project_id`). Deactivated
Students stay Members and count towards the Team size.
"""

from sqlalchemy.orm import Session

from pmp_backend.domain import Role
from pmp_backend.errors import Conflict, NotFound, Refused
from pmp_backend.models import Project, User
from pmp_backend.services.projects import changeable_project

MOVE_CONFIRMATION_NEEDED = "move_confirmation_needed"


class MoveConfirmationNeededError(Conflict):
    """The Student is a Member elsewhere; the client must ask before moving."""

    code = MOVE_CONFIRMATION_NEEDED


def add_member(
    session: Session, project_id: int, student_id: int, *, confirm_move: bool = False
) -> Project:
    """Make a Student a Member; moving them from another Project needs confirmation."""
    project = changeable_project(session, project_id)  # locked, refused if archived
    # Locked too, so the same Student cannot be placed twice at the same moment.
    student = session.get(User, student_id, with_for_update=True)
    if student is None or student.role != Role.STUDENT.value:
        raise Refused("Only Students can be Members.")
    if not student.is_active:
        raise Refused(
            f"{student.full_name} is deactivated and cannot be added as a new Member."
        )
    if student.project_id == project.id:
        raise Conflict(f"{student.full_name} is already a Member of {project.title}.")
    if project.member_count >= project.team_size_max:
        raise Conflict(
            f"{project.title} is full ({project.team_size_label}). "
            "Raise the maximum Team size first."
        )
    if student.project is not None and not confirm_move:
        raise MoveConfirmationNeededError(
            f"{student.full_name} is a Member of {student.project.title}. "
            f"Move {student.full_name} to {project.title}?"
        )
    # One update: leaving the old Project and joining this one happen together.
    student.project = project
    session.commit()
    session.refresh(project)
    return project


def remove_member(session: Session, project_id: int, student_id: int) -> Project:
    project = changeable_project(session, project_id)  # locked, refused if archived
    student = session.get(User, student_id)
    if student is None or student.project_id != project.id:
        raise NotFound(f"This Student is not a Member of {project.title}.")
    student.project = None
    session.commit()
    session.refresh(project)
    return project
