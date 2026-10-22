"""The Project Chat (spec #91): one group chat per Project.

Its Chat people are the Members, the Product Owner and the Guests; every
Teacher and the Superuser can also read and write in every Chat. Unread counts
come from how far each User read a Chat (`ChatRead`).
"""

from dataclasses import dataclass

from sqlalchemy import and_, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from pmp_backend.domain import ProjectStatus, Role
from pmp_backend.errors import Conflict, Forbidden, NotFound, Refused
from pmp_backend.models import ChatGuest, ChatMessage, ChatRead, Project, User
from pmp_backend.services.projects import get_project
from pmp_backend.services.users import get_user

MAX_LENGTH = 4000
# The newest messages a Chat opens with; older ones come later (search, #97).
PAGE = 200


class ChatError(Refused):
    """A Chat action was refused; the message is fit to show."""


class ChatForbiddenError(ChatError, Forbidden):
    pass


class ChatConflictError(ChatError, Conflict):
    pass


class ChatNotFoundError(ChatError, NotFound):
    pass


def is_staff(user: User) -> bool:
    return user.role in (Role.TEACHER, Role.SUPERUSER)


def is_team(user: User, project: Project) -> bool:
    """A Member or the Product Owner."""
    return user.project_id == project.id or user.id == project.product_owner_id


def guest_project_ids(session: Session, user: User) -> set[int]:
    """The Projects in whose Chat the User is a Guest."""
    return set(
        session.scalars(
            select(ChatGuest.project_id).where(ChatGuest.user_id == user.id)
        )
    )


def is_guest(session: Session, user: User, project: Project) -> bool:
    return session.get(ChatGuest, (project.id, user.id)) is not None


def is_chat_person(session: Session, user: User, project: Project) -> bool:
    """A Member, the Product Owner or a Guest: whom the Chat is for. Guests lose
    access when the Project is archived."""
    if is_team(user, project):
        return True
    active = project.status == ProjectStatus.ACTIVE.value
    return active and is_guest(session, user, project)


def readable_project(session: Session, user: User, project_id: int) -> Project:
    """The Project whose Chat `user` may read; refused otherwise."""
    project = get_project(session, project_id)
    if not (is_staff(user) or is_chat_person(session, user, project)):
        raise ChatForbiddenError("You don't have access to this chat.")
    return project


def writable_project(session: Session, user: User, project_id: int) -> Project:
    """The Project whose Chat `user` may write in: Archived ones are read-only."""
    project = readable_project(session, user, project_id)
    if project.status == ProjectStatus.ARCHIVED.value:
        raise ChatConflictError(f"{project.title} is archived: its chat is read-only.")
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
    project = writable_project(session, user, project_id)
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


def _visible_projects(
    session: Session, user: User, guest_ids: set[int]
) -> list[Project]:
    """Staff see every Active Project's Chat; Students their own Project's and
    those where they are a Guest."""
    query = select(Project).where(Project.status == ProjectStatus.ACTIVE.value)
    if not is_staff(user):
        own = {user.project_id} if user.project_id is not None else set()
        if not own | guest_ids:
            return []
        query = query.where(Project.id.in_(own | guest_ids))
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


def chats(session: Session, user: User, *, mine: bool = False) -> list[ChatSummary]:
    """The Chats the User sees (with `mine`: only those where they are one of the
    Chat people), by title, with their Unread counts."""
    guest_ids = guest_project_ids(session, user)
    projects = _visible_projects(session, user, guest_ids)
    counts = _unread_counts(session, user, [project.id for project in projects])
    summaries = [
        ChatSummary(
            project.id,
            project.title,
            counts.get(project.id, 0),
            is_team(user, project) or project.id in guest_ids,
        )
        for project in projects
    ]
    return [summary for summary in summaries if summary.mine or not mine]


def unread_total(session: Session, user: User) -> tuple[int, bool]:
    """The badge: Unread messages in the User's own Chats (for Teachers, those
    where they are the Product Owner or a Guest), and whether they have any Chat
    at all."""
    summaries = chats(session, user)
    mine = [summary for summary in summaries if summary.mine]
    return sum(summary.unread for summary in mine), bool(summaries)


# Who is in a Chat.

MEMBER, PRODUCT_OWNER, GUEST = "Member", "Product Owner", "Guest"


@dataclass(frozen=True)
class ChatPerson:
    user: User
    # MEMBER, PRODUCT_OWNER or GUEST.
    kind: str


def people(session: Session, user: User, project_id: int) -> list[ChatPerson]:
    """The Chat people: the Product Owner, the Members, then the Guests."""
    project = readable_project(session, user, project_id)
    found = [ChatPerson(project.product_owner, PRODUCT_OWNER)]
    found += [ChatPerson(member, MEMBER) for member in project.members]
    if project.status == ProjectStatus.ACTIVE.value:
        found += [ChatPerson(guest.user, GUEST) for guest in _guests(session, project)]
    return found


def _guests(session: Session, project: Project) -> list[ChatGuest]:
    return list(
        session.scalars(
            select(ChatGuest)
            .join(ChatGuest.user)
            .where(ChatGuest.project_id == project.id)
            .order_by(User.last_name, User.first_name)
        )
    )


def _managed_project(session: Session, actor: User, project_id: int) -> Project:
    """The Project whose Guests `actor` may change: staff only, Active only."""
    if not is_staff(actor):
        raise ChatForbiddenError(
            "Only the Product Owner, Teachers and the Superuser add or remove Guests."
        )
    return writable_project(session, actor, project_id)


def guest_candidates(session: Session, actor: User, project_id: int) -> list[User]:
    """Active Users who could be added as a Guest: not yet one of the Chat people."""
    project = _managed_project(session, actor, project_id)
    inside = {person.user.id for person in people(session, actor, project.id)}
    users = session.scalars(
        select(User)
        .where(User.is_active.is_(True))
        .order_by(User.last_name, User.first_name)
    )
    return [user for user in users if user.id not in inside]


def add_guest(session: Session, actor: User, project_id: int, user_id: int) -> User:
    project = _managed_project(session, actor, project_id)
    guest = get_user(session, user_id)
    if not guest.is_active:
        raise ChatError(f"{guest.full_name} is deactivated, so can't join a chat.")
    if is_team(guest, project) or is_guest(session, guest, project):
        raise ChatConflictError(f"{guest.full_name} is already in this chat.")
    session.add(ChatGuest(project_id=project.id, user_id=guest.id))
    session.commit()
    return guest


def remove_guest(session: Session, actor: User, project_id: int, user_id: int) -> None:
    """Staff remove a Guest; a Guest may also leave the Chat themselves."""
    if actor.id == user_id:
        project = writable_project(session, actor, project_id)
    else:
        project = _managed_project(session, actor, project_id)
    guest = session.get(ChatGuest, (project.id, user_id))
    if guest is None:
        raise ChatNotFoundError("This person is not a Guest in this chat.")
    session.delete(guest)
    session.commit()
