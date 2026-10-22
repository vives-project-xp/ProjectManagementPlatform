"""The Project Chat (spec #91): a Student's Chat, the Chats screen for Teachers
and the Superuser, and one Chat's page, kept up to date by polling (ADR 0008)."""

import html
import re
from contextlib import suppress
from typing import Any

from nicegui import ui
from starlette.responses import Response

from pmp_frontend import api
from pmp_frontend.shell import ErrorMessage, guard, page_frame, role_page, token
from pmp_frontend.times import shown

STAFF = {"superuser", "teacher"}
# How often an open Chat asks for new messages (ADR 0008).
POLL_SECONDS = 2.0
MAX_LENGTH = 4000
# A web link, without trailing punctuation such as the full stop ending a sentence.
URL = re.compile(r"https?://[^\s<>\"']*[^\s<>\"'.,;:!?)\]]")

CHATS_COLUMNS = [
    {"name": "title", "label": "Project", "field": "title", "align": "left"},
    {"name": "unread", "label": "Unread", "field": "unread", "align": "left"},
]
UNREAD_CELL = """
<q-td :props="props">
  <q-badge v-if="props.value > 0" color="primary" :label="props.value" />
</q-td>
"""


def linked(text: str) -> str:
    """A message as HTML: escaped, with its web links clickable (new tab)."""
    parts = []
    last = 0
    for match in URL.finditer(text):
        parts.append(html.escape(text[last : match.start()]))
        url = html.escape(match.group(0))
        parts.append(
            f'<a href="{url}" target="_blank" rel="noopener noreferrer">{url}</a>'
        )
        last = match.end()
    parts.append(html.escape(text[last:]))
    return "".join(parts)


def _message(message: dict[str, Any]) -> None:
    """One message: your own on the right on sand, others' on the left."""
    mine = message["mine"]
    author = message["author"]["name"] if message["author"] else "Deleted user"
    with ui.row().classes("w-full" + (" justify-end" if mine else "")):
        bubble = "bg-[#efeee9]" if mine else "bg-white border"
        with (
            ui.column()
            .classes(f"gap-0 max-w-[80%] rounded-lg px-3 py-2 {bubble}")
            .mark(f"message-{message['id']}")
        ):
            ui.label(f"{author} · {shown(message['created_at'])}").classes(
                "text-caption"
            ).style("color: #666666")
            # Escaped by `linked`, so no sanitising needed.
            ui.html(linked(message["body"]), sanitize=False).classes(
                "whitespace-pre-wrap break-words"
            ).mark("message-body")


async def chat_view(project_id: int) -> None:
    """A Chat: its messages, new ones appearing within seconds, and the send box."""
    try:
        chat = await api.chat(token(), project_id)
        first = await api.chat_messages(token(), project_id)
    except api.ApiError as error:
        ui.label(error.message)
        return
    seen: set[int] = set()
    state: dict[str, Any] = {"last": 0, "empty": None}

    def show(messages: list[dict[str, Any]]) -> bool:
        """Add the messages not shown yet; whether there were any."""
        new = [message for message in messages if message["id"] not in seen]
        if new and state["empty"] is not None:
            state["empty"].delete()
            state["empty"] = None
        with column:
            for message in new:
                _message(message)
                seen.add(message["id"])
                state["last"] = max(state["last"], message["id"])
        if new:
            ui.timer(0.1, lambda: scroll.scroll_to(percent=1.0), once=True)
        return bool(new)

    async def read() -> None:
        if state["last"]:
            # Only the badge depends on it; the next poll tries again.
            with suppress(api.ApiError):
                await api.mark_chat_read(token(), project_id, state["last"])

    async def poll() -> None:
        try:
            new = await api.chat_messages(token(), project_id, after=state["last"])
        except api.ApiError:
            # Shown again on the next try; a Deploy takes a minute.
            return
        if show(new):
            await read()

    async def send() -> None:
        body = (box.value or "").strip()
        if not body:
            return
        try:
            sent = await api.send_chat_message(token(), project_id, body)
        except api.ApiError as error:
            send_error.show(error.message)
            return
        send_error.hide()
        box.value = ""
        show([sent])

    ui.label(f"Chat: {chat['title']}").classes("text-h4").mark("chat-title")
    with ui.card().classes("w-full p-0"):
        scroll = ui.scroll_area().classes("w-full h-[60vh]").mark("chat-messages")
        with scroll:
            column = ui.column().classes("w-full gap-2 p-2")
        if not first:
            with column:
                state["empty"] = ui.label("No messages yet.").classes("text-caption")
        show(first)
    await read()
    if chat["read_only"]:
        ui.label("This Project is archived: its chat is read-only.")
    else:
        with ui.row().classes("w-full items-end no-wrap"):
            box = (
                ui.textarea(placeholder="Write a message…")
                .props(f"autogrow outlined dense maxlength={MAX_LENGTH}")
                .classes("grow")
                .mark("chat-input")
            )
            ui.button(icon="send", on_click=send).props("round").mark("chat-send")
        # Enter sends; Shift+Enter starts a new line.
        box.on("keydown.enter.exact.prevent", send)
        send_error = ErrorMessage()
    ui.timer(POLL_SECONDS, poll)


def register() -> None:
    @role_page("/chat", "Chat", {"student"})
    async def student_chat(user: api.CurrentUser) -> None:
        found = await api.chats(token())
        if not found:
            ui.label("Chat").classes("text-h4")
            ui.label("You'll have a chat once you're a Member of a Project.")
            return
        await chat_view(found[0]["project_id"])

    @role_page("/chats", "Chats", STAFF)
    async def chats_page(user: api.CurrentUser) -> None:
        ui.label("Chats").classes("text-h4")
        found = await api.chats(token())
        if not found:
            ui.label("No Active Projects, so no chats yet.")
            return
        table = ui.table(columns=CHATS_COLUMNS, rows=found, row_key="project_id")
        table.classes("w-full").mark("chats")
        table.add_slot("body-cell-unread", UNREAD_CELL)
        table.on(
            "rowClick",
            lambda event: ui.navigate.to(f"/chats/{event.args[1]['project_id']}"),
        )

    @ui.page("/chats/{project_id}")
    async def chat_page(project_id: int) -> Response | None:
        user = await guard()
        if isinstance(user, Response):
            return user
        with page_frame("Chat", user):
            if user.role in STAFF:
                ui.link("← Chats", "/chats").classes("text-dark")
            await chat_view(project_id)
        return None
