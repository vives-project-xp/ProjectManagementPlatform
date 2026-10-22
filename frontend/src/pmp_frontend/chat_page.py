"""The Project Chat (spec #91): a Student's Chat, the Chats screen for Teachers
and the Superuser, and one Chat's page, kept up to date by polling (ADR 0008)."""

import html
import re
from contextlib import suppress
from typing import Any

from nicegui import ui
from starlette.responses import Response

from pmp_frontend import api
from pmp_frontend.shell import (
    ErrorMessage,
    confirm,
    guard,
    page_frame,
    role_page,
    token,
)
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

    with ui.row().classes("w-full items-center"):
        ui.label(f"Chat: {chat['title']}").classes("text-h4").mark("chat-title")
        ui.space()
        if chat["is_guest"]:
            ui.button(
                "Leave chat", icon="logout", on_click=lambda: _leave(project_id)
            ).props("outline color=dark").mark("leave-chat")
    await _people(project_id, chat)
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


async def _leave(project_id: int) -> None:
    question = "Leave this chat? You can only come back when someone adds you again."
    if not await confirm(question, "Leave"):
        return
    try:
        await api.leave_chat(token(), project_id)
    except api.ApiError as error:
        ui.notify(error.message, type="negative")
        return
    ui.notify("You left the chat.")
    ui.navigate.to("/")


async def _people(project_id: int, chat: dict[str, Any]) -> None:
    """Who is in the Chat (Product Owner, Members, Guests); staff add and remove
    Guests here."""
    manage = chat["can_manage_guests"]

    async def remove(person: dict[str, Any]) -> None:
        if not await confirm(f"Remove {person['name']} from this chat?", "Remove"):
            return
        try:
            await api.remove_chat_guest(token(), project_id, person["id"])
        except api.ApiError as error:
            ui.notify(error.message, type="negative")
            return
        ui.notify(f"{person['name']} was removed from the chat.")
        people_list.refresh()

    async def open_add_dialog() -> None:
        candidates = await api.chat_guest_candidates(token(), project_id)

        async def add() -> None:
            if choice.value is None:
                error.show("Choose a person first.")
                return
            try:
                added = await api.add_chat_guest(token(), project_id, choice.value)
            except api.ApiError as problem:
                error.show(problem.message)
                return
            dialog.close()
            ui.notify(f"{added['name']} joined the chat as a Guest.")
            people_list.refresh()

        with ui.dialog() as dialog, ui.card().classes("w-full max-w-md"):
            ui.label("Add a Guest").classes("text-h6")
            ui.label(
                "Guests read the whole chat and write like the team, until they "
                "leave or are removed."
            ).classes("text-caption")
            choice = (
                ui.select(
                    {person["id"]: person["name"] for person in candidates},
                    label="Person",
                    with_input=True,
                )
                .classes("w-full")
                .mark("guest-choice")
            )
            error = ErrorMessage()
            with ui.row():
                ui.button("Add", on_click=add).mark("confirm-add-guest")
                ui.button("Cancel", on_click=dialog.close).props("flat color=dark")
        dialog.open()

    @ui.refreshable
    async def people_list() -> None:
        try:
            found = await api.chat_people(token(), project_id)
        except api.ApiError as error:
            ui.label(error.message)
            return
        with (
            ui.expansion(f"People ({len(found)})", icon="group")
            .classes("w-full bg-white rounded-lg")
            .mark("chat-people")
        ):
            for person in found:
                with ui.row().classes("w-full items-center"):
                    ui.label(person["name"]).mark(f"person-{person['id']}")
                    ui.label(person["kind"]).classes("text-caption").style(
                        "color: #666666"
                    )
                    ui.space()
                    if manage and person["kind"] == "Guest":
                        ui.button("Remove", on_click=lambda p=person: remove(p)).props(
                            "flat dense color=dark"
                        ).mark(f"remove-guest-{person['id']}")
            if manage:
                ui.button(
                    "Add Guest", icon="person_add", on_click=open_add_dialog
                ).props("outline color=dark").mark("add-guest")

    await people_list()


def _chats_table(found: list[dict[str, Any]]) -> None:
    """Chats by title with their Unread count; a row opens its Chat."""
    table = ui.table(columns=CHATS_COLUMNS, rows=found, row_key="project_id")
    table.classes("w-full").mark("chats")
    table.add_slot("body-cell-unread", UNREAD_CELL)
    table.on(
        "rowClick",
        lambda event: ui.navigate.to(f"/chats/{event.args[1]['project_id']}"),
    )


def register() -> None:
    @role_page("/chat", "Chat", {"student"})
    async def student_chat(user: api.CurrentUser) -> None:
        found = await api.chats(token())
        if len(found) == 1:
            await chat_view(found[0]["project_id"])
            return
        ui.label("Chat").classes("text-h4")
        if not found:
            ui.label("You'll have a chat once you're a Member of a Project.")
            return
        # Their own Project's Chat and those where they are a Guest.
        _chats_table(found)

    @role_page("/chats", "Chats", STAFF)
    async def chats_page(user: api.CurrentUser) -> None:
        ui.label("Chats").classes("text-h4")
        only_mine = ui.switch(
            "Only my chats", value=True, on_change=lambda: listed.refresh()
        ).mark("only-my-chats")

        @ui.refreshable
        async def listed() -> None:
            found = await api.chats(token(), mine=only_mine.value)
            if found:
                _chats_table(found)
            elif only_mine.value:
                ui.label(
                    "You're not in any chat yet: Projects where you are the Product "
                    'Owner or a Guest appear here. Turn off "Only my chats" to see '
                    "every chat."
                )
            else:
                ui.label("No Active Projects, so no chats yet.")

        await listed()

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
