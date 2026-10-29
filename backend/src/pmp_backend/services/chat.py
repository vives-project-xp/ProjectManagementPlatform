"""The Project Chat (spec #91): one group chat per Project.

Its Chat people are the Members, the Product Owner and the Guests; every
Teacher and the Superuser can also read and write in every Chat. Unread counts
come from how far each User read a Chat (`ChatRead`).
"""

import asyncio
import logging
import re
import shutil
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path, PurePath
from zoneinfo import ZoneInfo

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy import delete as delete_rows
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from pmp_backend.domain import ProjectStatus, Role
from pmp_backend.errors import Conflict, Forbidden, NotFound, Refused
from pmp_backend.models import (
    CHAT_REACTIONS,
    ChatFile,
    ChatGuest,
    ChatMention,
    ChatMessage,
    ChatReaction,
    ChatRead,
    Project,
    User,
    chat_revision,
)
from pmp_backend.services.projects import get_project
from pmp_backend.services.users import get_user

log = logging.getLogger(__name__)
BRUSSELS = ZoneInfo("Europe/Brussels")

MAX_LENGTH = 4000
# The newest messages a Chat opens with; older ones come later (search, #97).
PAGE = 200
# Photos and files per message, and the size of each.
MAX_FILES = 5
MAX_FILE_BYTES = 10 * 1024 * 1024
# Programs and scripts that run when opened: never accepted.
REFUSED_EXTENSIONS = frozenset(
    [
        ".apk",
        ".app",
        ".bat",
        ".cmd",
        ".com",
        ".cpl",
        ".deb",
        ".dll",
        ".dmg",
        ".exe",
        ".hta",
        ".jar",
        ".lnk",
        ".msc",
        ".msi",
        ".pif",
        ".ps1",
        ".reg",
        ".rpm",
        ".scr",
        ".sh",
        ".vbe",
        ".vbs",
        ".wsf",
        ".wsh",
    ]
)
# Windows programs (MZ) and Linux ones (ELF), whatever their name.
PROGRAM_SIGNATURES = (b"MZ", b"\x7fELF")
# The first bytes of each photo format shown as a thumbnail, by extension.
IMAGE_TYPES = {
    ".jpg": ("image/jpeg", b"\xff\xd8\xff"),
    ".jpeg": ("image/jpeg", b"\xff\xd8\xff"),
    ".png": ("image/png", b"\x89PNG\r\n\x1a\n"),
    ".gif": ("image/gif", b"GIF8"),
    ".webp": ("image/webp", b"RIFF"),
}
OTHER_FILE = "application/octet-stream"
# "Is typing…" lasts this long after the last keystroke.
TYPING_SECONDS = 5.0
# The most search results shown, newest first.
SEARCH_LIMIT = 50


@dataclass(frozen=True)
class Upload:
    name: str
    # May hold one byte more than allowed, so that a too large file is recognised.
    data: bytes


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
    """A Member, the Product Owner or a Guest: whom the Chat is for. An Archived
    Project's Chat is for nobody: only Teachers and the Superuser still read it."""
    if project.status != ProjectStatus.ACTIVE.value:
        return False
    return is_team(user, project) or is_guest(session, user, project)


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
    session: Session, user: User, project_id: int, since: int | None = None
) -> list[ChatMessage]:
    """With `since`: every message sent, edited or deleted after that revision,
    in the order they changed. Without: the newest PAGE, oldest first."""
    readable_project(session, user, project_id)
    query = select(ChatMessage).where(ChatMessage.project_id == project_id)
    if since is not None:
        return list(
            session.scalars(
                query.where(ChatMessage.revision > since).order_by(ChatMessage.revision)
            )
        )
    newest = session.scalars(query.order_by(ChatMessage.id.desc()).limit(PAGE))
    return list(reversed(list(newest)))


class TypingBoard:
    """Who is typing in which Chat. Kept in memory (one backend process, like
    the LoginGuard); an entry is forgotten TYPING_SECONDS after the last
    keystroke, or when the person sends their message."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        # Per Project: user id -> (first name, when they last typed).
        self._typing: dict[int, dict[int, tuple[str, float]]] = {}

    def typed(self, project_id: int, user: User) -> None:
        self._typing.setdefault(project_id, {})[user.id] = (
            user.first_name,
            self._clock(),
        )

    def stopped(self, project_id: int, user_id: int) -> None:
        self._typing.get(project_id, {}).pop(user_id, None)

    def names(self, project_id: int, viewer: User) -> list[str]:
        """The first names of those typing now, except the viewer, by name."""
        since = self._clock() - TYPING_SECONDS
        current = {
            user_id: entry
            for user_id, entry in self._typing.get(project_id, {}).items()
            if entry[1] > since
        }
        if current:
            self._typing[project_id] = current
        else:
            self._typing.pop(project_id, None)
        return sorted(
            name for user_id, (name, _) in current.items() if user_id != viewer.id
        )


def typing(session: Session, board: TypingBoard, user: User, project_id: int) -> None:
    """The User is typing; only the Chat people show as typing."""
    project = writable_project(session, user, project_id)
    if is_chat_person(session, user, project):
        board.typed(project.id, user)


def read_marks(session: Session, user: User, project_id: int) -> list[tuple[User, int]]:
    """How far each of the Chat people (not the User, not staff who only read
    along) has read the Chat: drives "Seen by"."""
    project = readable_project(session, user, project_id)
    people = {person.user.id: person.user for person in _chat_people(session, project)}
    people.pop(user.id, None)
    marks = dict(
        session.execute(
            select(ChatRead.user_id, ChatRead.last_read_id).where(
                ChatRead.project_id == project.id, ChatRead.user_id.in_(people)
            )
        ).all()
    )
    return [(person, marks.get(person.id, 0)) for person in people.values()]


def search(
    session: Session,
    user: User,
    project_id: int,
    text: str = "",
    author_id: int | None = None,
    files_only: bool = False,
) -> list[ChatMessage]:
    """Messages whose text or file names contain `text` (any case), optionally
    by one person and only those with files; newest first, at most
    SEARCH_LIMIT. Deleted messages are never found."""
    readable_project(session, user, project_id)
    text = text.strip()
    if not text and author_id is None and not files_only:
        raise ChatError("Type something to search for.")
    query = select(ChatMessage).where(
        ChatMessage.project_id == project_id, ChatMessage.deleted_at.is_(None)
    )
    if text:
        pattern = "%" + re.sub(r"([\\%_])", r"\\\1", text) + "%"
        in_files = (
            select(ChatFile.id)
            .where(ChatFile.message_id == ChatMessage.id, ChatFile.name.ilike(pattern))
            .exists()
        )
        query = query.where(or_(ChatMessage.body.ilike(pattern), in_files))
    if author_id is not None:
        query = query.where(ChatMessage.author_id == author_id)
    if files_only:
        query = query.where(
            select(ChatFile.id).where(ChatFile.message_id == ChatMessage.id).exists()
        )
    return list(
        session.scalars(query.order_by(ChatMessage.id.desc()).limit(SEARCH_LIMIT))
    )


def _message_in(session: Session, user: User, message_id: int) -> ChatMessage:
    """A message in a Chat the User can write in, not yet deleted."""
    message = session.get(ChatMessage, message_id)
    if message is None:
        raise ChatNotFoundError("This message doesn't exist.")
    writable_project(session, user, message.project_id)
    if message.deleted_at is not None:
        raise ChatConflictError("This message was deleted.")
    return message


def _changed(session: Session, message: ChatMessage, *, replies: bool = True) -> None:
    """Give the message a new revision, and (when its text changed) the replies
    quoting it too, so open Chats show the change."""
    which = ChatMessage.id == message.id
    if replies:
        which = or_(which, ChatMessage.reply_to_id == message.id)
    session.execute(
        update(ChatMessage).where(which).values(revision=chat_revision.next_value())
    )


def _mention(session: Session, message: ChatMessage, project: Project) -> None:
    """Record who the message mentions: Chat people by "@First Last", and every
    Member by "@team"; never its author."""
    text = message.body.lower()
    found: set[int] = set()
    if "@" in text:
        if re.search(r"@team(?!\w)", text):
            found |= {member.id for member in project.members}
        for person in _chat_people(session, project):
            name = re.escape(person.user.full_name.lower())
            if re.search(rf"@{name}(?!\w)", text):
                found.add(person.user.id)
    found.discard(message.author_id)
    message.mentions[:] = [m for m in message.mentions if m.user_id in found]
    known = {m.user_id for m in message.mentions}
    message.mentions += [ChatMention(user_id=i) for i in sorted(found - known)]


def react(
    session: Session, user: User, message_id: int, emoji: str, *, on: bool
) -> ChatMessage:
    """Add (`on`) or take back the User's reaction; adding twice changes nothing."""
    if emoji not in CHAT_REACTIONS:
        raise ChatError("React with " + " ".join(CHAT_REACTIONS) + " only.")
    message = _message_in(session, user, message_id)
    mine = [r for r in message.reactions if r.user_id == user.id and r.emoji == emoji]
    if on and not mine:
        message.reactions.append(ChatReaction(user_id=user.id, emoji=emoji))
    elif not on and mine:
        message.reactions.remove(mine[0])
    else:
        return message
    session.flush()
    _changed(session, message, replies=False)
    session.commit()
    session.refresh(message)
    return message


def edit(session: Session, user: User, message_id: int, body: str) -> ChatMessage:
    """Change the text of your own message; shown "(edited)"."""
    message = _message_in(session, user, message_id)
    if message.author_id != user.id:
        raise ChatForbiddenError("You can only edit your own messages.")
    body = body.strip()
    if not body and not message.files:
        raise ChatError("Write a message first.")
    if len(body) > MAX_LENGTH:
        raise ChatError(f"A message can be at most {MAX_LENGTH} characters.")
    message.body = body
    message.edited_at = func.now()
    _mention(session, message, get_project(session, message.project_id))
    session.flush()
    _changed(session, message)
    session.commit()
    session.refresh(message)
    return message


def delete(session: Session, files_dir: Path, user: User, message_id: int) -> None:
    """Delete your own message, or any message as a Teacher or the Superuser:
    its text and files go, the row stays ("This message was deleted.")."""
    message = _message_in(session, user, message_id)
    if message.author_id != user.id and not is_staff(user):
        raise ChatForbiddenError("You can only delete your own messages.")
    paths = [_file_path(files_dir, message.project_id, f.id) for f in message.files]
    message.body = ""
    message.deleted_at = func.now()
    message.files.clear()
    message.reactions.clear()
    message.mentions.clear()
    session.flush()
    _changed(session, message)
    session.commit()
    for path in paths:
        path.unlink(missing_ok=True)


def send(
    session: Session,
    user: User,
    project_id: int,
    body: str,
    uploads: Sequence[Upload] = (),
    files_dir: Path | None = None,
    reply_to_id: int | None = None,
) -> ChatMessage:
    """Post a message: text, photos and files, or both, optionally as a reply to
    another message in the same Chat. `files_dir` is needed when there are
    `uploads`."""
    project = writable_project(session, user, project_id)
    if reply_to_id is not None:
        original = session.get(ChatMessage, reply_to_id)
        if original is None or original.project_id != project.id:
            raise ChatError("You can only reply to a message in this chat.")
        if original.deleted_at is not None:
            raise ChatError("This message was deleted, so you can't reply to it.")
    body = body.strip()
    if not body and not uploads:
        raise ChatError("Write a message or attach a file first.")
    if len(body) > MAX_LENGTH:
        raise ChatError(f"A message can be at most {MAX_LENGTH} characters.")
    _check_uploads(uploads)
    message = ChatMessage(
        project_id=project.id, author_id=user.id, body=body, reply_to_id=reply_to_id
    )
    session.add(message)
    _mention(session, message, project)
    session.flush()
    written = _attach(session, files_dir, message, uploads) if uploads else []
    # Your own message is never Unread for you.
    _read_up_to(session, user, project.id, message.id)
    try:
        session.commit()
    except Exception:
        for path in written:
            path.unlink(missing_ok=True)
        raise
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
    # An Unread message mentions the User (the red @ marker).
    mentioned: bool = False


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


def _unread(session: Session, user: User, project_ids: list[int]) -> dict:
    """Per Project: how many messages by others came after the User's read
    mark, and whether one of them mentions the User."""
    if not project_ids:
        return {}
    read_mark = func.coalesce(ChatRead.last_read_id, 0)
    mentioned = (
        select(ChatMention.message_id)
        .where(
            ChatMention.message_id == ChatMessage.id,
            ChatMention.user_id == user.id,
        )
        .exists()
    )
    rows = session.execute(
        select(ChatMessage.project_id, func.count(), func.bool_or(mentioned))
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
            ChatMessage.deleted_at.is_(None),
            or_(ChatMessage.author_id.is_(None), ChatMessage.author_id != user.id),
        )
        .group_by(ChatMessage.project_id)
    )
    return {project_id: (count, bool(me)) for project_id, count, me in rows.all()}


def chats(session: Session, user: User, *, mine: bool = False) -> list[ChatSummary]:
    """The Chats the User sees (with `mine`: only those where they are one of the
    Chat people), by title, with their Unread counts."""
    guest_ids = guest_project_ids(session, user)
    projects = _visible_projects(session, user, guest_ids)
    unread = _unread(session, user, [project.id for project in projects])
    summaries = [
        ChatSummary(
            project.id,
            project.title,
            unread.get(project.id, (0, False))[0],
            is_team(user, project) or project.id in guest_ids,
            unread.get(project.id, (0, False))[1],
        )
        for project in projects
    ]
    return [summary for summary in summaries if summary.mine or not mine]


@dataclass(frozen=True)
class UnreadTotal:
    count: int
    # Whether the User has any Chat at all.
    has_chat: bool
    # An Unread message in one of them mentions the User.
    mentioned: bool


def unread_total(session: Session, user: User) -> UnreadTotal:
    """The badge: Unread messages in the User's own Chats (for Teachers, those
    where they are the Product Owner or a Guest)."""
    summaries = chats(session, user)
    mine = [summary for summary in summaries if summary.mine]
    return UnreadTotal(
        sum(summary.unread for summary in mine),
        bool(summaries),
        any(summary.mentioned for summary in summaries),
    )


# Who is in a Chat.

MEMBER, PRODUCT_OWNER, GUEST = "Member", "Product Owner", "Guest"


@dataclass(frozen=True)
class ChatPerson:
    user: User
    # MEMBER, PRODUCT_OWNER or GUEST.
    kind: str


def people(session: Session, user: User, project_id: int) -> list[ChatPerson]:
    """The Chat people: the Product Owner, the Members, then the Guests."""
    return _chat_people(session, readable_project(session, user, project_id))


def _chat_people(session: Session, project: Project) -> list[ChatPerson]:
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


# Archived Chats are deleted this long after archiving.
KEEP_ARCHIVED = timedelta(days=182)
# How often the background loop looks for Chats to delete.
CLEAN_UP_EVERY_SECONDS = 24 * 60 * 60


def deleted_on(project: Project) -> date | None:
    """The day an Archived Project's Chat will be deleted (Belgian time)."""
    if project.archived_at is None:
        return None
    return (project.archived_at + KEEP_ARCHIVED).astimezone(BRUSSELS).date()


def clean_up(session: Session, files_dir: Path) -> list[int]:
    """Delete the messages and files of the Chats of Projects archived more than
    KEEP_ARCHIVED ago; the ids of those Projects. Restoring one later starts an
    empty Chat."""
    expired = list(
        session.scalars(
            select(Project.id).where(
                Project.status == ProjectStatus.ARCHIVED.value,
                Project.archived_at < func.now() - KEEP_ARCHIVED,
                select(ChatMessage.id)
                .where(ChatMessage.project_id == Project.id)
                .exists(),
            )
        )
    )
    if not expired:
        return []
    # Files, reactions and mentions go with their messages (ON DELETE CASCADE).
    session.execute(delete_rows(ChatMessage).where(ChatMessage.project_id.in_(expired)))
    session.execute(delete_rows(ChatRead).where(ChatRead.project_id.in_(expired)))
    session.commit()
    for project_id in expired:
        discard_files(files_dir, project_id)
    return expired


async def clean_up_forever(make_session: sessionmaker, files_dir: Path) -> None:
    """Once a day, delete the expired Chats; never crashes the backend."""

    def run_once() -> None:
        with make_session() as session:
            deleted = clean_up(session, files_dir)
        if deleted:
            log.info("Deleted the chats of archived Projects %s", deleted)

    while True:
        try:
            await asyncio.to_thread(run_once)
        except Exception:
            log.exception("The chat clean-up failed")
        await asyncio.sleep(CLEAN_UP_EVERY_SECONDS)


# Photos and files.


def _clean_name(name: str) -> str:
    """The uploaded name without any folder part, at most 255 characters."""
    base = PurePath(name.replace("\\", "/")).name.strip() or "file"
    stem, dot, extension = base.rpartition(".")
    if len(base) <= 255:
        return base
    if dot and len(extension) < 20:
        return stem[: 254 - len(extension)] + "." + extension
    return base[:255]


def _extension(name: str) -> str:
    return PurePath(name).suffix.lower()


def _check_uploads(uploads: Sequence[Upload]) -> None:
    if len(uploads) > MAX_FILES:
        raise ChatError(f"A message can have at most {MAX_FILES} photos or files.")
    for upload in uploads:
        name = _clean_name(upload.name)
        if len(upload.data) > MAX_FILE_BYTES:
            raise ChatError(f"{name} is larger than 10 MB.")
        if not upload.data:
            raise ChatError(f"{name} is empty.")
        if _extension(name) in REFUSED_EXTENSIONS or upload.data.startswith(
            PROGRAM_SIGNATURES
        ):
            raise ChatError(f"{name} is a program, and programs can't be sent.")


def _media_type(name: str, data: bytes) -> str:
    """An image type only when the bytes really are that photo format."""
    kind, start = IMAGE_TYPES.get(_extension(name), (OTHER_FILE, None))
    if start is None or not data.startswith(start):
        return OTHER_FILE
    if kind == "image/webp" and data[8:12] != b"WEBP":
        return OTHER_FILE
    return kind


def _file_path(files_dir: Path, project_id: int, file_id: int) -> Path:
    # Never the uploaded name, so nothing outside the folder can be written.
    return files_dir / str(project_id) / str(file_id)


def _attach(
    session: Session, files_dir: Path | None, message: ChatMessage, uploads
) -> list[Path]:
    """Add the uploads to the message and write them; the paths written."""
    assert files_dir is not None, "files_dir is needed for uploads"
    rows = []
    for upload in uploads:
        name = _clean_name(upload.name)
        row = ChatFile(
            name=name,
            size=len(upload.data),
            media_type=_media_type(name, upload.data),
        )
        message.files.append(row)
        rows.append((row, upload.data))
    session.flush()
    written: list[Path] = []
    try:
        for row, data in rows:
            path = _file_path(files_dir, message.project_id, row.id)
            path.parent.mkdir(parents=True, exist_ok=True)
            # Written under another name first, so a failed write leaves no file.
            partial = path.with_name(f"{row.id}.partial")
            partial.write_bytes(data)
            partial.replace(path)
            written.append(path)
    except OSError:
        for path in written:
            path.unlink(missing_ok=True)
        raise
    return written


def read_file(
    session: Session, files_dir: Path, user: User, file_id: int
) -> tuple[ChatFile, bytes]:
    """A file and its bytes, for whoever can read its Chat."""
    found = session.get(ChatFile, file_id)
    message = session.get(ChatMessage, found.message_id) if found else None
    if found is None or message is None:
        raise ChatNotFoundError("This file doesn't exist (any more).")
    readable_project(session, user, message.project_id)
    path = _file_path(files_dir, message.project_id, found.id)
    if not path.is_file():
        raise ChatNotFoundError("This file doesn't exist (any more).")
    return found, path.read_bytes()


def discard_files(files_dir: Path, project_id: int) -> None:
    """Delete the Chat files of a deleted Project."""
    shutil.rmtree(files_dir / str(project_id), ignore_errors=True)
