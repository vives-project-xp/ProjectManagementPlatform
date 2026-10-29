from datetime import datetime
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, File, Form, Response, UploadFile, status
from pydantic import BaseModel

from pmp_backend.api.deps import CurrentUserDep, SessionDep, SettingsDep
from pmp_backend.api.schemas import PersonOut
from pmp_backend.domain import ProjectStatus
from pmp_backend.models import ChatFile, ChatMessage, User
from pmp_backend.services import chat

router = APIRouter(prefix="/api", tags=["chat"])


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


class MessageOut(BaseModel):
    id: int
    # None: a Deleted User.
    author: PersonOut | None
    # Empty when the message is only photos or files.
    body: str
    files: list[FileOut]
    created_at: datetime
    mine: bool

    @classmethod
    def of(cls, message: ChatMessage, user: User) -> "MessageOut":
        author = message.author
        return cls(
            id=message.id,
            author=PersonOut.of(author) if author else None,
            body=message.body,
            files=[FileOut.of(file) for file in message.files],
            created_at=message.created_at,
            mine=message.author_id == user.id,
        )


class ReadIn(BaseModel):
    message_id: int


class ChatSummaryOut(BaseModel):
    project_id: int
    title: str
    unread: int
    mine: bool


class UnreadOut(BaseModel):
    count: int
    # Whether the User has any Chat (Students without a Project have none).
    has_chat: bool


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
    after: int | None = None,
) -> list[MessageOut]:
    """Oldest first: every message after `after`, or the newest ones."""
    found = chat.messages(session, user, project_id, after)
    return [MessageOut.of(message, user) for message in found]


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
) -> MessageOut:
    """A form with the text in `body` and up to 5 photos or files in `files`."""
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
        session, user, project_id, body, uploads, settings.chat_files_dir
    )
    return MessageOut.of(message, user)


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
        )
        for summary in chat.chats(session, user, mine=mine)
    ]


@router.get("/chats/unread")
def unread(session: SessionDep, user: CurrentUserDep) -> UnreadOut:
    count, has_chat = chat.unread_total(session, user)
    return UnreadOut(count=count, has_chat=has_chat)
