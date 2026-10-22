from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Response, status
from pydantic import BaseModel, StringConstraints

from pmp_backend.api.deps import CurrentUserDep, SessionDep
from pmp_backend.api.schemas import PersonOut
from pmp_backend.domain import ProjectStatus
from pmp_backend.models import ChatMessage, User
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


class MessageIn(BaseModel):
    body: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True, min_length=1, max_length=chat.MAX_LENGTH
        ),
    ]


class MessageOut(BaseModel):
    id: int
    # None: a Deleted User.
    author: PersonOut | None
    body: str
    created_at: datetime
    mine: bool

    @classmethod
    def of(cls, message: ChatMessage, user: User) -> "MessageOut":
        author = message.author
        return cls(
            id=message.id,
            author=PersonOut.of(author) if author else None,
            body=message.body,
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
    project_id: int, body: MessageIn, session: SessionDep, user: CurrentUserDep
) -> MessageOut:
    return MessageOut.of(chat.send(session, user, project_id, body.body), user)


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
