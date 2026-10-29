"""The Project Chat (spec #91): a Student's Chat, the Chats screen for Teachers
and the Superuser, and one Chat's page, kept up to date by polling (ADR 0008)."""

import html
import re
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from typing import Any

from nicegui import app, events, ui
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
# Photos and files per message, and the size of each (the backend checks again).
MAX_FILES = 5
MAX_FILE_BYTES = 10 * 1024 * 1024
# The longest first line a quote shows (as the backend's).
QUOTE_LENGTH = 100
DELETED = "This message was deleted."
# A web link, without trailing punctuation such as the full stop ending a sentence.
URL = re.compile(r"https?://[^\s<>\"']*[^\s<>\"'.,;:!?)\]]")

CHATS_COLUMNS = [
    {"name": "title", "label": "Project", "field": "title", "align": "left"},
    {"name": "unread", "label": "Unread", "field": "unread", "align": "left"},
]
# The Unread count, with a red @ while an Unread message mentions the User.
UNREAD_CELL = """
<q-td :props="props">
  <q-badge v-if="props.value > 0" color="primary" :label="props.value" />
  <q-badge v-if="props.row.mentioned" outline color="primary" label="@"
           class="q-ml-xs" />
</q-td>
"""
# The six reactions, in the order shown, with the names used in markers.
REACTIONS = {
    "👍": "thumbs-up",
    "❤️": "heart",
    "😂": "laugh",
    "😮": "wow",
    "😢": "sad",
    "🎉": "party",
}
# "@" and what was typed after it, at the end of the text box.
TYPING_MENTION = re.compile(r"(?:^|\s)@([^@\n]{0,40})$")


def _with_mentions(text: str, names: list[str]) -> str:
    """Plain text as HTML, with @team and @<name> of the Chat people in bold."""
    if "@" not in text:
        return html.escape(text)
    options = sorted([*names, "team"], key=len, reverse=True)
    pattern = re.compile(
        "@(?:" + "|".join(re.escape(name) for name in options) + r")(?!\w)",
        re.IGNORECASE,
    )
    parts = []
    last = 0
    for match in pattern.finditer(text):
        parts.append(html.escape(text[last : match.start()]))
        parts.append(f"<b>{html.escape(match.group(0))}</b>")
        last = match.end()
    parts.append(html.escape(text[last:]))
    return "".join(parts)


def linked(text: str, names: list[str] | None = None) -> str:
    """A message as HTML: escaped, with its web links clickable (new tab) and
    mentions of `names` (and @team) in bold."""
    parts = []
    last = 0
    for match in URL.finditer(text):
        parts.append(_with_mentions(text[last : match.start()], names or []))
        url = html.escape(match.group(0))
        parts.append(
            f'<a href="{url}" target="_blank" rel="noopener noreferrer">{url}</a>'
        )
        last = match.end()
    parts.append(_with_mentions(text[last:], names or []))
    return "".join(parts)


def file_size(size: int) -> str:
    """A file size as people read it: 820 B, 14 KB, 3.2 MB."""
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{round(size / 1024)} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def file_url(file: dict[str, Any]) -> str:
    return f"/chat-files/{file['id']}"


def _show_full(file: dict[str, Any]) -> None:
    with ui.dialog() as dialog, ui.card().classes("max-w-[95vw]"):
        ui.image(file_url(file)).props("fit=contain").classes(
            "w-[80vw] max-w-5xl h-[75vh]"
        ).mark("full-photo")
        with ui.row().classes("w-full items-center"):
            ui.link(file["name"], file_url(file), new_tab=True).classes("text-dark")
            ui.space()
            ui.button("Close", on_click=dialog.close).props("flat color=dark")
    dialog.open()


def _files(files: list[dict[str, Any]]) -> None:
    """Photos as thumbnails that open full size; other files as downloads."""
    photos = [file for file in files if file["is_image"]]
    others = [file for file in files if not file["is_image"]]
    if photos:
        with ui.row().classes("gap-2 py-1"):
            for photo in photos:
                ui.image(file_url(photo)).classes(
                    "w-40 h-28 rounded cursor-pointer"
                ).on("click", lambda p=photo: _show_full(p)).mark(
                    f"chat-photo-{photo['id']}"
                )
    for other in others:
        with (
            ui.row()
            .classes("items-center gap-1 no-wrap")
            .mark(f"chat-file-{other['id']}")
        ):
            ui.icon("description").style("color: #666666")
            ui.link(other["name"], file_url(other)).classes("text-dark break-all")
            ui.label(f"({file_size(other['size'])})").classes("text-caption").style(
                "color: #666666"
            )


def author_name(message: dict[str, Any]) -> str:
    return message["author"]["name"] if message["author"] else "Deleted user"


def first_line(message: dict[str, Any]) -> str:
    """What a quote of the message shows: its first line, or its first file."""
    lines = message["body"].splitlines()
    first = lines[0] if lines else ""
    if not first and message["files"]:
        first = message["files"][0]["name"]
    return first if len(first) <= QUOTE_LENGTH else first[: QUOTE_LENGTH - 1] + "…"


@dataclass(frozen=True)
class _Actions:
    """What a message's menu and quote do in an open Chat."""

    # False in an Archived (read-only) Chat: no menu.
    writable: bool
    reply: Callable[[dict[str, Any]], None]
    edit: Callable[[dict[str, Any]], Awaitable[None]]
    delete: Callable[[dict[str, Any]], Awaitable[None]]
    # Scroll to the message with this id.
    go_to: Callable[[int], None]
    # Add (True) or take back (False) the User's reaction.
    react: Callable[[dict[str, Any], str, bool], Awaitable[None]]
    # The Chat people's names, for showing mentions.
    names: list[str]


def _quote(quote: dict[str, Any], go_to: Callable[[int], None], marker: str) -> None:
    """The quoted original above a reply; a click scrolls to it."""
    text = DELETED if quote["deleted"] else quote["first_line"]
    with (
        ui.column()
        .classes("gap-0 border-l-4 pl-2 mb-1 cursor-pointer")
        .style("border-color: #e00020")
        .on("click", lambda: go_to(quote["id"]))
        .mark(marker)
    ):
        ui.label(quote["author_name"]).classes("text-caption text-bold")
        ui.label(text).classes("text-caption" + (" italic" if quote["deleted"] else ""))


def _menu(message: dict[str, Any], actions: _Actions) -> None:
    number = message["id"]
    with (
        ui.button(icon="more_vert")
        .props("flat dense round size=sm color=dark")
        .mark(f"message-menu-{number}"),
        ui.menu(),
    ):
        ui.menu_item("Reply", on_click=lambda: actions.reply(message)).mark(
            f"reply-{number}"
        )
        if message["can_edit"]:
            ui.menu_item("Edit", on_click=lambda: actions.edit(message)).mark(
                f"edit-{number}"
            )
        if message["can_delete"]:
            ui.menu_item("Delete", on_click=lambda: actions.delete(message)).mark(
                f"delete-{number}"
            )


def _reactions(message: dict[str, Any], actions: _Actions) -> None:
    """The reactions with their counts (names on hover); a click on one adds or
    takes back yours, and the smiley adds another."""
    number = message["id"]
    can_react = actions.writable and not message["deleted"]
    if not message["reactions"] and not can_react:
        return
    with ui.row().classes("items-center gap-1 pt-1").mark(f"reactions-{number}"):
        for reaction in message["reactions"]:
            emoji = reaction["emoji"]
            button = (
                ui.button(
                    f"{emoji} {reaction['count']}",
                    on_click=lambda e=emoji, m=reaction["mine"]: actions.react(
                        message, e, not m
                    ),
                )
                .props(
                    'dense no-caps unelevated rounded padding="2px 8px" '
                    + (
                        "color=primary outline"
                        if reaction["mine"]
                        else "flat color=dark"
                    )
                )
                .mark(f"reaction-{number}-{REACTIONS[emoji]}")
            )
            button.tooltip(", ".join(reaction["names"]))
            button.set_enabled(can_react)
        if can_react:
            with (
                ui.button(icon="add_reaction")
                .props("flat dense round size=sm color=dark")
                .mark(f"react-{number}"),
                ui.menu(),
                ui.row().classes("gap-0 p-1 no-wrap"),
            ):
                for emoji, name in REACTIONS.items():
                    ui.button(
                        emoji, on_click=lambda e=emoji: actions.react(message, e, True)
                    ).props("flat dense size=lg").mark(f"react-{number}-{name}")


def _message(message: dict[str, Any], actions: _Actions) -> None:
    """One message: your own on the right on sand, others' on the left."""
    mine = message["mine"]
    with ui.row().classes("w-full" + (" justify-end" if mine else "")):
        bubble = "bg-[#efeee9]" if mine else "bg-white border"
        if message["mentions_me"]:
            # Meant for you: a red line on the left (accent, not text colour).
            bubble += " border-l-4 border-l-[#e00020]"
        with (
            ui.column()
            .classes(f"gap-0 max-w-[80%] rounded-lg px-3 py-2 {bubble}")
            .mark(
                f"message-{message['id']}"
                + (f" mentioned-{message['id']}" if message["mentions_me"] else "")
            )
        ):
            with ui.row().classes("w-full items-center gap-1 no-wrap"):
                edited = " · (edited)" if message["edited"] else ""
                ui.label(
                    f"{author_name(message)} · {shown(message['created_at'])}{edited}"
                ).classes("text-caption").style("color: #666666")
                if actions.writable and not message["deleted"]:
                    ui.space()
                    _menu(message, actions)
            if message["reply_to"]:
                _quote(message["reply_to"], actions.go_to, f"quote-{message['id']}")
            if message["deleted"]:
                ui.label(DELETED).classes("italic").style("color: #666666").mark(
                    "message-deleted"
                )
                return
            if message["body"]:
                # Escaped by `linked`, so no sanitising needed.
                ui.html(linked(message["body"], actions.names), sanitize=False).classes(
                    "chat-text whitespace-pre-wrap break-words"
                ).mark("message-body")
            _files(message["files"])
            _reactions(message, actions)


async def chat_view(project_id: int) -> None:
    """A Chat: its messages, new ones appearing within seconds, and the send box."""
    try:
        chat = await api.chat(token(), project_id)
        first = await api.chat_messages(token(), project_id)
        people = await api.chat_people(token(), project_id)
    except api.ApiError as error:
        ui.label(error.message)
        return
    # Each shown message's element and the revision it shows.
    rows: dict[int, ui.element] = {}
    revisions: dict[int, int] = {}
    # last: the newest message id (read mark); since: the newest revision
    # fetched; oldest: the first message shown (older ones are not loaded).
    state: dict[str, Any] = {
        "last": 0,
        "since": max((m["revision"] for m in first), default=0),
        "oldest": min((m["id"] for m in first), default=None),
        "empty": None,
        "reply_to": None,
        # The text being typed, for the @ suggestions.
        "draft": "",
    }

    def show(messages: list[dict[str, Any]]) -> bool:
        """Add new messages and redraw changed ones; whether any were new."""
        added = False
        for message in messages:
            number = message["id"]
            if number not in rows:
                if state["oldest"] is not None and number < state["oldest"]:
                    continue
                if state["empty"] is not None:
                    state["empty"].delete()
                    state["empty"] = None
                with column:
                    rows[number] = ui.element("div").classes("w-full")
                state["last"] = max(state["last"], number)
                added = True
            elif revisions[number] >= message["revision"]:
                continue
            revisions[number] = message["revision"]
            rows[number].clear()
            with rows[number]:
                _message(message, actions)
        if added:
            ui.timer(0.1, lambda: scroll.scroll_to(percent=1.0), once=True)
        return added

    async def read() -> None:
        if state["last"]:
            # Only the badge depends on it; the next poll tries again.
            with suppress(api.ApiError):
                await api.mark_chat_read(token(), project_id, state["last"])

    async def poll() -> None:
        try:
            changed = await api.chat_messages(token(), project_id, since=state["since"])
        except api.ApiError:
            # Shown again on the next try; a Deploy takes a minute.
            return
        # Only what was fetched moves `since`: a message you just sent may have
        # a newer revision than others' messages not fetched yet.
        state["since"] = max([state["since"]] + [m["revision"] for m in changed])
        if show(changed):
            await read()

    def go_to(message_id: int) -> None:
        if message_id not in rows:
            ui.notify("That message is older than the ones shown here.")
            return
        ui.run_javascript(
            f"document.getElementById('c{rows[message_id].id}')"
            ".scrollIntoView({behavior: 'smooth', block: 'center'})"
        )

    def reply(message: dict[str, Any]) -> None:
        state["reply_to"] = message
        replying.refresh()
        box.run_method("focus")

    def stop_replying() -> None:
        state["reply_to"] = None
        replying.refresh()

    async def edit(message: dict[str, Any]) -> None:
        async def save() -> None:
            try:
                edited = await api.edit_chat_message(
                    token(), message["id"], text.value or ""
                )
            except api.ApiError as problem:
                error.show(problem.message)
                return
            dialog.close()
            show([edited])

        with ui.dialog() as dialog, ui.card().classes("w-full max-w-lg"):
            ui.label("Edit message").classes("text-h6")
            text = (
                ui.textarea(value=message["body"])
                .props(f"autogrow outlined maxlength={MAX_LENGTH}")
                .classes("w-full")
                .mark("edit-input")
            )
            error = ErrorMessage()
            with ui.row():
                ui.button("Save", on_click=save).mark("save-edit")
                ui.button("Cancel", on_click=dialog.close).props("flat color=dark")
        dialog.open()

    async def delete(message: dict[str, Any]) -> None:
        if not await confirm("Delete this message? Its files go too.", "Delete"):
            return
        try:
            await api.delete_chat_message(token(), message["id"])
        except api.ApiError as error:
            ui.notify(error.message, type="negative")
            return
        await poll()

    async def react(message: dict[str, Any], emoji: str, on: bool) -> None:
        change = api.add_chat_reaction if on else api.remove_chat_reaction
        try:
            changed = await change(token(), message["id"], emoji)
        except api.ApiError as error:
            ui.notify(error.message, type="negative")
            return
        show([changed])

    # Who can be mentioned: the Chat people (staff who only read along can't).
    names = [person["name"] for person in people]
    actions = _Actions(
        writable=not chat["read_only"],
        reply=reply,
        edit=edit,
        delete=delete,
        go_to=go_to,
        react=react,
        names=names,
    )

    @ui.refreshable
    def suggestions() -> None:
        """While "@…" is being typed: the Chat people (and team) it may mean."""
        typing = TYPING_MENTION.search(state["draft"])
        if typing is None:
            return
        typed = typing.group(1).lower()
        options = [name for name in [*names, "team"] if name.lower().startswith(typed)]
        if not options:
            return
        with ui.row().classes("w-full items-center gap-1").mark("mention-suggestions"):
            ui.label("Mention:").classes("text-caption").style("color: #666666")
            for name in options[:8]:
                ui.button(f"@{name}", on_click=lambda n=name: mention(n)).props(
                    "flat dense no-caps color=dark"
                ).mark("mention-option")

    def typed() -> None:
        state["draft"] = box.value or ""
        suggestions.refresh()

    def mention(name: str) -> None:
        """Put "@name " in place of the "@…" being typed."""
        text = box.value or ""
        typing = TYPING_MENTION.search(text)
        if typing is not None:
            text = text[: typing.start(1) - 1]
        box.value = f"{text}@{name} "
        box.run_method("focus")

    # Photos and files picked for the next message: (name, bytes, media type).
    pending: list[tuple[str, bytes, str]] = []

    async def send() -> None:
        body = (box.value or "").strip()
        if not body and not pending:
            return
        original = state["reply_to"]
        try:
            sent = await api.send_chat_message(
                token(),
                project_id,
                body,
                pending,
                reply_to_id=original["id"] if original else None,
            )
        except api.ApiError as error:
            send_error.show(error.message)
            return
        send_error.hide()
        box.value = ""
        pending.clear()
        attachments.refresh()
        uploader.set_visibility(False)
        stop_replying()
        show([sent])

    @ui.refreshable
    def replying() -> None:
        """The message the next one answers, with a way to stop replying."""
        original = state["reply_to"]
        if original is None:
            return
        with ui.row().classes("w-full items-center no-wrap").mark("chat-replying"):
            ui.icon("reply").style("color: #666666")
            ui.label(f"Replying to {author_name(original)}: {first_line(original)}")
            ui.space()
            ui.button(icon="close", on_click=stop_replying).props(
                "flat dense round color=dark"
            ).mark("stop-replying")

    async def picked(event: events.MultiUploadEventArguments) -> None:
        for file in event.files:
            pending.append((file.name, await file.read(), file.content_type))
        uploader.reset()
        if len(pending) > MAX_FILES:
            del pending[MAX_FILES:]
            send_error.show(f"A message can have at most {MAX_FILES} photos or files.")
        attachments.refresh()

    def unpick(index: int) -> None:
        del pending[index]
        attachments.refresh()

    @ui.refreshable
    def attachments() -> None:
        """The photos and files that go with the next message."""
        if not pending:
            return
        with ui.row().classes("w-full gap-1").mark("chat-attachments"):
            for index, (name, data, _) in enumerate(pending):
                ui.chip(
                    f"{name} ({file_size(len(data))})",
                    icon="attach_file",
                    removable=True,
                    on_value_change=lambda _, i=index: unpick(i),
                ).props("outline color=dark")

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
        replying()
        attachments()
        suggestions()
        with ui.row().classes("w-full items-end no-wrap"):
            ui.button(
                icon="attach_file",
                on_click=lambda: uploader.set_visibility(not uploader.visible),
            ).props("round flat color=dark").tooltip("Add photos or files").mark(
                "chat-attach"
            )
            box = (
                ui.textarea(placeholder="Write a message…")
                .props(f"autogrow outlined dense maxlength={MAX_LENGTH}")
                .classes("grow")
                .mark("chat-input")
            )
            ui.button(icon="send", on_click=send).props("round").mark("chat-send")
        uploader = (
            ui.upload(
                label=f"Photos or files: at most {MAX_FILES}, 10 MB each, no programs",
                multiple=True,
                auto_upload=True,
                max_files=MAX_FILES,
                max_file_size=MAX_FILE_BYTES,
                on_multi_upload=picked,
                # Too many or too large; the browser does not say which.
                on_rejected=lambda: send_error.show(
                    f"At most {MAX_FILES} photos or files of 10 MB each."
                ),
            )
            .props("flat bordered")
            .classes("w-full")
            .mark("chat-upload")
        )
        uploader.set_visibility(False)
        box.on_value_change(typed)
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
    @app.get("/chat-files/{file_id}")
    async def chat_file(file_id: int) -> Response:
        """A Chat photo or file, fetched with the User's token (like /photos)."""
        if not token():
            return Response(status_code=401)
        try:
            found = await api.chat_file(token(), file_id)
        except api.ApiError as error:
            return Response(status_code=error.status_code)
        # A file never changes once sent, so the browser may keep it a while.
        return Response(
            found.content,
            media_type=found.headers["content-type"],
            headers={
                "Content-Disposition": found.headers["content-disposition"],
                "Cache-Control": "private, max-age=86400",
            },
        )

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
