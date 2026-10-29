from datetime import datetime
from typing import Annotated
from urllib.parse import quote

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from pydantic import BaseModel
from sqlalchemy.orm import Session

from pmp_backend.api.deps import CurrentUserDep, SessionDep, SettingsDep
from pmp_backend.api.schemas import PersonOut
from pmp_backend.domain import ProjectStatus
from pmp_backend.models import CHAT_REACTIONS, ChatFile, ChatMessage, User
from pmp_backend.services import chat

router = APIRouter(prefix="/api", tags=["chat"])

# The longest first line a quote shows.
QUOTE_LENGTH = 100


class ChatOut(BaseModel):
    project_id: int
    title: str
    # Archived Projects' Chats are read-only.
    read_only: bool
    # Teachers and the Superuser add and remove Guests.
    can_manage_guests: bool
    # The User is a Guest here, so they may leave.
    is_guest: bool


class ChatPersonOut(PersonOut):
    # "Member", "Product Owner" or "Guest".
    kind: str


class GuestIn(BaseModel):
    user_id: int


class FileOut(BaseModel):
    id: int
    name: str
    # In bytes.
    size: int
    # A photo, shown as a thumbnail; other files are downloads.
    is_image: bool

    @classmethod
    def of(cls, file: ChatFile) -> "FileOut":
        return cls(
            id=file.id,
            name=file.name,
            size=file.size,
            is_image=file.media_type != chat.OTHER_FILE,
        )


def _author_name(message: ChatMessage) -> str:
    return message.author.full_name if message.author else "Deleted user"


class QuoteOut(BaseModel):
    """The message a reply answers: its author and first line."""

    id: int
    author_name: str
    # Empty when it was deleted.
    first_line: str
    deleted: bool

    @classmethod
    def of(cls, message: ChatMessage) -> "QuoteOut":
        lines = message.body.splitlines()
        first = lines[0] if lines else ""
        if not first and message.files:
            first = message.files[0].name
        if len(first) > QUOTE_LENGTH:
            first = first[: QUOTE_LENGTH - 1].rstrip() + "…"
        return cls(
            id=message.id,
            author_name=_author_name(message),
            first_line=first,
            deleted=message.deleted_at is not None,
        )


class ReactionOut(BaseModel):
    emoji: str
    count: int
    # Who reacted, shown on hover.
    names: list[str]
    # The User reacted with it; clicking takes it back.
    mine: bool


def _reactions(message: ChatMessage, user: User) -> list[ReactionOut]:
    """The message's reactions in the fixed order, only those someone gave."""
    found = []
    for emoji in CHAT_REACTIONS:
        given = [r for r in message.reactions if r.emoji == emoji]
        if given:
            found.append(
                ReactionOut(
                    emoji=emoji,
                    count=len(given),
                    names=[r.user.full_name for r in given],
                    mine=any(r.user_id == user.id for r in given),
                )
            )
    return found


class MessageOut(BaseModel):
    id: int
    # None: a Deleted User.
    author: PersonOut | None
    # Empty when the message is only photos or files, or was deleted.
    body: str
    files: list[FileOut]
    created_at: datetime
    mine: bool
    # Grows with every change; ask for messages `since` the highest one seen.
    revision: int
    edited: bool
    deleted: bool
    # The message this one replies to; None when it isn't a reply.
    reply_to: QuoteOut | None
    reactions: list[ReactionOut]
    # It mentions the User (@name or @team): shown highlighted.
    mentions_me: bool
    # On the User's own messages: the Chat people who have read it (staff who
    # only read along don't count). None on others' and deleted messages.
    seen_by: list[str] | None
    # What the User may do with it (Archived Chats aside: they are read-only).
    can_edit: bool
    can_delete: bool

    @classmethod
    def of(
        cls,
        message: ChatMessage,
        user: User,
        marks: list[tuple[User, int]] | None = None,
    ) -> "MessageOut":
        """`marks`: chat.read_marks of the message's Chat, for `seen_by`."""
        author = message.author
        mine = message.author_id == user.id
        deleted = message.deleted_at is not None
        seen_by = None
        if mine and not deleted:
            seen_by = [
                person.full_name for person, last in marks or [] if last >= message.id
            ]
        return cls(
            id=message.id,
            author=PersonOut.of(author) if author else None,
            body=message.body,
            files=[FileOut.of(file) for file in message.files],
            created_at=message.created_at,
            mine=mine,
            revision=message.revision,
            edited=message.edited_at is not None,
            deleted=deleted,
            reply_to=QuoteOut.of(message.reply_to) if message.reply_to else None,
            reactions=_reactions(message, user),
            mentions_me=any(m.user_id == user.id for m in message.mentions),
            seen_by=seen_by,
            can_edit=mine and not deleted,
            can_delete=(mine or chat.is_staff(user)) and not deleted,
        )


class EditIn(BaseModel):
    body: str


class ReadMarkOut(BaseModel):
    """How far one of the Chat people has read: the last message id they saw."""

    name: str
    last_read_id: int


class UpdatesOut(BaseModel):
    """What an open Chat asks for every ~2 seconds (ADR 0008)."""

    # Sent, edited or deleted since the revision asked for.
    messages: list["MessageOut"]
    # First names of the others typing now: "Anna is typing…".
    typing: list[str]
    # The other Chat people's read marks, to keep "Seen by" up to date.
    reads: list[ReadMarkOut]


def _out(
    session: Session, user: User, project_id: int, messages: list[ChatMessage]
) -> list[MessageOut]:
    """The messages of one Chat, with "Seen by" on the User's own."""
    marks = chat.read_marks(session, user, project_id)
    return [MessageOut.of(message, user, marks) for message in messages]


def _one(session: Session, user: User, message: ChatMessage) -> MessageOut:
    return _out(session, user, message.project_id, [message])[0]


def get_typing(request: Request) -> chat.TypingBoard:
    return request.app.state.chat_typing


TypingDep = Annotated[chat.TypingBoard, Depends(get_typing)]


class ReadIn(BaseModel):
    message_id: int


class ChatSummaryOut(BaseModel):
    project_id: int
    title: str
    unread: int
    mine: bool
    # An Unread message mentions the User: the red @ marker.
    mentioned: bool


class UnreadOut(BaseModel):
    count: int
    # Whether the User has any Chat (Students without a Project have none).
    has_chat: bool
    # An Unread message in one of their Chats mentions them.
    mentioned: bool


@router.get("/projects/{project_id}/chat")
def get_chat(project_id: int, session: SessionDep, user: CurrentUserDep) -> ChatOut:
    project = chat.readable_project(session, user, project_id)
    read_only = project.status == ProjectStatus.ARCHIVED.value
    return ChatOut(
        project_id=project.id,
        title=project.title,
        read_only=read_only,
        can_manage_guests=chat.is_staff(user) and not read_only,
        is_guest=chat.is_guest(session, user, project) and not read_only,
    )


@router.get("/projects/{project_id}/chat/people")
def chat_people(
    project_id: int, session: SessionDep, user: CurrentUserDep
) -> list[ChatPersonOut]:
    """The Product Owner, the Members, then the Guests."""
    return [
        ChatPersonOut(**PersonOut.of(person.user).model_dump(), kind=person.kind)
        for person in chat.people(session, user, project_id)
    ]


@router.get("/projects/{project_id}/chat/guests/candidates")
def guest_candidates(
    project_id: int, session: SessionDep, user: CurrentUserDep
) -> list[PersonOut]:
    """Active Users who could join as a Guest (Teachers and the Superuser)."""
    return [
        PersonOut.of(candidate)
        for candidate in chat.guest_candidates(session, user, project_id)
    ]


@router.post("/projects/{project_id}/chat/guests", status_code=status.HTTP_201_CREATED)
def add_guest(
    project_id: int, body: GuestIn, session: SessionDep, user: CurrentUserDep
) -> PersonOut:
    return PersonOut.of(chat.add_guest(session, user, project_id, body.user_id))


@router.delete(
    "/projects/{project_id}/chat/guests/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_guest(
    project_id: int, user_id: int, session: SessionDep, user: CurrentUserDep
) -> Response:
    """Teachers and the Superuser remove a Guest; a Guest leaves with their own id."""
    chat.remove_guest(session, user, project_id, user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/projects/{project_id}/chat/messages")
def list_messages(
    project_id: int,
    session: SessionDep,
    user: CurrentUserDep,
    since: int | None = None,
) -> list[MessageOut]:
    """The newest messages, oldest first; with `since` (a revision): every
    message sent, edited or deleted after it, in the order they changed."""
    found = chat.messages(session, user, project_id, since)
    return _out(session, user, project_id, found)


@router.get("/projects/{project_id}/chat/updates")
def updates(
    project_id: int,
    since: int,
    session: SessionDep,
    user: CurrentUserDep,
    board: TypingDep,
) -> UpdatesOut:
    """Messages changed since revision `since`, who is typing and how far the
    others have read."""
    found = chat.messages(session, user, project_id, since)
    marks = chat.read_marks(session, user, project_id)
    return UpdatesOut(
        messages=[MessageOut.of(message, user, marks) for message in found],
        typing=board.names(project_id, user),
        reads=[
            ReadMarkOut(name=person.full_name, last_read_id=last)
            for person, last in marks
        ],
    )


@router.post(
    "/projects/{project_id}/chat/typing", status_code=status.HTTP_204_NO_CONTENT
)
def typing(
    project_id: int, session: SessionDep, user: CurrentUserDep, board: TypingDep
) -> Response:
    """Send while typing (every few seconds); shown to the others for 5 s."""
    chat.typing(session, board, user, project_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/projects/{project_id}/chat/search")
def search(
    project_id: int,
    session: SessionDep,
    user: CurrentUserDep,
    q: str = "",
    from_: Annotated[int | None, Query(alias="from")] = None,
    files_only: bool = False,
) -> list[MessageOut]:
    """Text and file names containing `q`, by person `from` (a user id), only
    messages with files; newest first, at most 50."""
    found = chat.search(session, user, project_id, q, from_, files_only)
    return _out(session, user, project_id, found)


@router.post(
    "/projects/{project_id}/chat/messages", status_code=status.HTTP_201_CREATED
)
def send_message(
    project_id: int,
    session: SessionDep,
    settings: SettingsDep,
    user: CurrentUserDep,
    body: Annotated[str, Form()] = "",
    files: Annotated[list[UploadFile], File()] = [],  # noqa: B006
    reply_to_id: Annotated[int | None, Form()] = None,
    *,
    board: TypingDep,
) -> MessageOut:
    """A form with the text in `body`, up to 5 photos or files in `files`, and
    optionally the message it replies to in `reply_to_id`."""
    if len(files) > chat.MAX_FILES:
        # Refused before reading any of them.
        uploads = [chat.Upload(file.filename or "file", b"") for file in files]
    else:
        # One byte more than allowed is enough to know a file is too large.
        uploads = [
            chat.Upload(
                file.filename or "file", file.file.read(chat.MAX_FILE_BYTES + 1)
            )
            for file in files
        ]
    message = chat.send(
        session,
        user,
        project_id,
        body,
        uploads,
        settings.chat_files_dir,
        reply_to_id=reply_to_id,
    )
    board.stopped(project_id, user.id)
    return _one(session, user, message)


@router.put("/chat/messages/{message_id}")
def edit_message(
    message_id: int, body: EditIn, session: SessionDep, user: CurrentUserDep
) -> MessageOut:
    """Your own messages only."""
    return _one(session, user, chat.edit(session, user, message_id, body.body))


@router.put("/chat/messages/{message_id}/reactions/{emoji}")
def add_reaction(
    message_id: int, emoji: str, session: SessionDep, user: CurrentUserDep
) -> MessageOut:
    """One of 👍 ❤️ 😂 😮 😢 🎉; adding it again changes nothing."""
    message = chat.react(session, user, message_id, emoji, on=True)
    return _one(session, user, message)


@router.delete("/chat/messages/{message_id}/reactions/{emoji}")
def remove_reaction(
    message_id: int, emoji: str, session: SessionDep, user: CurrentUserDep
) -> MessageOut:
    message = chat.react(session, user, message_id, emoji, on=False)
    return _one(session, user, message)


@router.delete("/chat/messages/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_message(
    message_id: int, session: SessionDep, settings: SettingsDep, user: CurrentUserDep
) -> Response:
    """Your own messages; Teachers and the Superuser delete any message."""
    chat.delete(session, settings.chat_files_dir, user, message_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/chat-files/{file_id}")
def get_file(
    file_id: int, session: SessionDep, settings: SettingsDep, user: CurrentUserDep
) -> Response:
    """A photo (shown in the page) or another file (always downloaded, so the
    browser never runs what someone uploaded)."""
    found, data = chat.read_file(session, settings.chat_files_dir, user, file_id)
    shown = "inline" if found.media_type != chat.OTHER_FILE else "attachment"
    return Response(
        content=data,
        media_type=found.media_type,
        headers={
            "Content-Disposition": f"{shown}; filename*=UTF-8''{quote(found.name)}",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/projects/{project_id}/chat/read", status_code=status.HTTP_204_NO_CONTENT)
def mark_read(
    project_id: int, body: ReadIn, session: SessionDep, user: CurrentUserDep
) -> Response:
    chat.mark_read(session, user, project_id, body.message_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/projects/{project_id}/chat/leave", status_code=status.HTTP_204_NO_CONTENT
)
def leave_chat(project_id: int, session: SessionDep, user: CurrentUserDep) -> Response:
    """A Guest leaves the Chat."""
    chat.remove_guest(session, user, project_id, user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/chats")
def list_chats(
    session: SessionDep, user: CurrentUserDep, mine: bool = False
) -> list[ChatSummaryOut]:
    """With `mine`: only the Chats where the User is one of the Chat people."""
    return [
        ChatSummaryOut(
            project_id=summary.project_id,
            title=summary.title,
            unread=summary.unread,
            mine=summary.mine,
            mentioned=summary.mentioned,
        )
        for summary in chat.chats(session, user, mine=mine)
    ]


@router.get("/chats/unread")
def unread(session: SessionDep, user: CurrentUserDep) -> UnreadOut:
    total = chat.unread_total(session, user)
    return UnreadOut(
        count=total.count, has_chat=total.has_chat, mentioned=total.mentioned
    )
