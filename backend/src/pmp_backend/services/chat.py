"""The Project Chat (spec #91): one group chat per Project.

Its Chat people are the Members and the Product Owner; every Teacher and the
Superuser can also read and write in every Chat. Unread counts come from how far
each User read a Chat (`ChatRead`).
"""

from dataclasses import dataclass

from sqlalchemy import and_, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from pmp_backend.domain import ProjectStatus, Role
from pmp_backend.errors import Conflict, Forbidden, Refused
from pmp_backend.models import ChatMessage, ChatRead, Project, User
from pmp_backend.services.projects import get_project

MAX_LENGTH = 4000
# The newest messages a Chat opens with; older ones come later (search, #97).
PAGE = 200


class ChatError(Refused):
    """A Chat action was refused; the message is fit to show."""


class ChatForbiddenError(ChatError, Forbidden):
    pass


class ChatConflictError(ChatError, Conflict):
    pass


def is_staff(user: User) -> bool:
    return user.role in (Role.TEACHER, Role.SUPERUSER)


def is_chat_person(user: User, project: Project) -> bool:
    """A Member or the Product Owner: whom the Chat is for."""
    return user.project_id == project.id or user.id == project.product_owner_id


def can_read(user: User, project: Project) -> bool:
    return is_staff(user) or is_chat_person(user, project)


def readable_project(session: Session, user: User, project_id: int) -> Project:
    """The Project whose Chat `user` may read; refused otherwise."""
    project = get_project(session, project_id)
    if not can_read(user, project):
        raise ChatForbiddenError("You don't have access to this chat.")
    return project


def messages(
    session: Session, user: User, project_id: int, after: int | None = None
) -> list[ChatMessage]:
    """The Chat's messages, oldest first: all after message `after`, or else
    the newest PAGE."""
    readable_project(session, user, project_id)
    query = select(ChatMessage).where(ChatMessage.project_id == project_id)
    if after is not None:
        return list(
            session.scalars(
                query.where(ChatMessage.id > after).order_by(ChatMessage.id)
            )
        )
    newest = session.scalars(query.order_by(ChatMessage.id.desc()).limit(PAGE))
    return list(reversed(list(newest)))


def send(session: Session, user: User, project_id: int, body: str) -> ChatMessage:
    project = readable_project(session, user, project_id)
    if project.status == ProjectStatus.ARCHIVED.value:
        raise ChatConflictError(f"{project.title} is archived: its chat is read-only.")
    body = body.strip()
    if not body:
        raise ChatError("Write a message first.")
    if len(body) > MAX_LENGTH:
        raise ChatError(f"A message can be at most {MAX_LENGTH} characters.")
    message = ChatMessage(project_id=project.id, author_id=user.id, body=body)
    session.add(message)
    session.flush()
    # Your own message is never Unread for you.
    _read_up_to(session, user, project.id, message.id)
    session.commit()
    return message


def mark_read(session: Session, user: User, project_id: int, message_id: int) -> None:
    readable_project(session, user, project_id)
    _read_up_to(session, user, project_id, message_id)
    session.commit()


def _read_up_to(session: Session, user: User, project_id: int, message_id: int) -> None:
    """Move the User's read mark forward (never back) to `message_id`."""
    statement = insert(ChatRead).values(
        project_id=project_id, user_id=user.id, last_read_id=message_id
    )
    session.execute(
        statement.on_conflict_do_update(
            index_elements=[ChatRead.project_id, ChatRead.user_id],
            set_={
                "last_read_id": func.greatest(
                    ChatRead.last_read_id, statement.excluded.last_read_id
                )
            },
        )
    )


@dataclass(frozen=True)
class ChatSummary:
    project_id: int
    title: str
    unread: int
    # Whether it counts for the User's badge: they are one of its Chat people.
    mine: bool


def _visible_projects(session: Session, user: User) -> list[Project]:
    """Staff see every Active Project's Chat; Students their own Project's."""
    query = select(Project).where(Project.status == ProjectStatus.ACTIVE.value)
    if not is_staff(user):
        if user.project_id is None:
            return []
        query = query.where(Project.id == user.project_id)
    return list(session.scalars(query.order_by(func.lower(Project.title))))


def _unread_counts(session: Session, user: User, project_ids: list[int]) -> dict:
    """Per Project: messages by others after the User's read mark."""
    if not project_ids:
        return {}
    read_mark = func.coalesce(ChatRead.last_read_id, 0)
    rows = session.execute(
        select(ChatMessage.project_id, func.count())
        .outerjoin(
            ChatRead,
            and_(
                ChatRead.project_id == ChatMessage.project_id,
                ChatRead.user_id == user.id,
            ),
        )
        .where(
            ChatMessage.project_id.in_(project_ids),
            ChatMessage.id > read_mark,
            or_(ChatMessage.author_id.is_(None), ChatMessage.author_id != user.id),
        )
        .group_by(ChatMessage.project_id)
    )
    return dict(rows.all())


def chats(session: Session, user: User) -> list[ChatSummary]:
    """The Chats the User sees, by title, with their Unread counts."""
    projects = _visible_projects(session, user)
    counts = _unread_counts(session, user, [project.id for project in projects])
    return [
        ChatSummary(
            project.id,
            project.title,
            counts.get(project.id, 0),
            is_chat_person(user, project),
        )
        for project in projects
    ]


def unread_total(session: Session, user: User) -> tuple[int, bool]:
    """The badge: Unread messages in the User's own Chats (for Teachers, those of
    their Projects as Product Owner), and whether they have any Chat at all."""
    summaries = chats(session, user)
    mine = [summary for summary in summaries if summary.mine]
    return sum(summary.unread for summary in mine), bool(summaries)
