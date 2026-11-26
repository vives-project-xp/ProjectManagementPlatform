"""What every logged-in page shares: the session, the page guard and the header."""

import json
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Any

from fastapi.responses import RedirectResponse
from nicegui import app, ui
from nicegui.elements.mixins.value_element import ValueElement
from starlette.responses import Response

from pmp_frontend import api
from pmp_frontend.theme import frame

TOKEN_KEY = "token"

# The screens each Role sees, in navigation order, with their Material icon;
# the first is the Role's home page.
NAVIGATION: dict[str, list[tuple[str, str, str]]] = {
    "superuser": [
        ("Users", "/users", "group"),
        ("Projects", "/projects", "folder"),
        ("Members", "/members", "badge"),
        ("Programmes", "/programmes", "school"),
        ("Top 3", "/top3", "format_list_numbered"),
        ("Planning", "/planning", "event"),
        ("Chats", "/chats", "forum"),
        ("Post suggestions", "/post-suggestions", "auto_awesome"),
        ("Scheduled posts", "/scheduled-posts", "schedule_send"),
        ("Social media", "/social-media", "campaign"),
    ],
    "teacher": [
        ("Projects", "/projects", "folder"),
        ("Members", "/members", "badge"),
        ("Top 3", "/top3", "format_list_numbered"),
        ("Planning", "/planning", "event"),
        ("Chats", "/chats", "forum"),
        ("Post suggestions", "/post-suggestions", "auto_awesome"),
        ("Scheduled posts", "/scheduled-posts", "schedule_send"),
    ],
    "student": [
        ("My project", "/my-project", "work"),
        ("Weekly update", "/weekly-update", "edit_note"),
        ("Chat", "/chat", "chat"),
    ],
    # People outside VIVES who follow Projects (spec #132).
    "client": [
        ("My projects", "/my-projects", "visibility"),
        ("Chat", "/chat", "chat"),
    ],
}
# The navigation items that show the Unread badge (spec #91), and how often it
# is refreshed.
CHAT_PATHS = {"/chat", "/chats"}
# Only Students in a Project have a Weekly update (spec #110).
PROJECT_ONLY_PATHS = {"/weekly-update"}
BADGE_SECONDS = 10.0


def home(user: api.CurrentUser) -> str:
    return NAVIGATION[user.role][0][1]


def token() -> str:
    return app.storage.user.get(TOKEN_KEY, "")


async def guard(
    *, allow_temporary_password: bool = False
) -> api.CurrentUser | Response:
    """The logged-in User, or the redirect that sends them where they must go first."""
    if not token():
        return RedirectResponse("/login")
    try:
        user = await api.me(token())
    except api.ApiError as error:
        if error.is_unauthorized:
            app.storage.user.pop(TOKEN_KEY, None)
            return RedirectResponse("/login?expired=true")
        # Backend unreachable: the login page shows the system status.
        return RedirectResponse("/login")
    if user.must_change_password and not allow_temporary_password:
        return RedirectResponse("/account")
    return user


async def _logout() -> None:
    stored_token = app.storage.user.pop(TOKEN_KEY, None)
    if stored_token:
        # Forgetting the token is what logs out; a failing call changes nothing.
        with suppress(api.ApiError):
            await api.logout(stored_token)
    ui.navigate.to("/login")


def navigation(user: api.CurrentUser) -> None:
    """The left menu (R17): the Role's screens one under the other, then My
    account, the User's name and Log out at the bottom."""
    current = _current_path()
    with ui.column().classes("w-full h-full gap-0 no-wrap py-2"):
        # Until the Temporary password is changed, there is nowhere else to go.
        if not user.must_change_password:
            for label, path, icon in NAVIGATION[user.role]:
                if path in PROJECT_ONLY_PATHS and user.project_id is None:
                    continue
                link = _navigation_link(label, path, icon, current).mark("navigation")
                if path in CHAT_PATHS:
                    # A Student or Client without any Chat doesn't get the item.
                    _unread_badge(
                        link, hide_without_chat=user.role in ("student", "client")
                    )
        if not user.must_change_password:
            _browser_notifications()
        ui.space()
        ui.separator()
        if not user.must_change_password:
            _navigation_link("My account", "/account", "account_circle", current)
        ui.label(user.full_name).classes("px-5 pt-3 text-caption text-grey-8")
        ui.button("Log out", icon="logout", on_click=_logout).props(
            "flat no-caps align=left color=dark"
        ).classes("w-full px-5 font-normal")


def _current_path() -> str:
    with suppress(AttributeError, RuntimeError):
        return ui.context.client.request.url.path
    return ""


def _navigation_link(label: str, path: str, icon: str, current: str) -> ui.link:
    """One menu row; the screen you're on (or one of its details pages) gets a
    sand background and a red bar on the left."""
    # Icons stay black like the text (house style), always next to the label.
    active = current == path or current.startswith(f"{path}/")
    style = "bg-[#efeee9] border-l-4 border-[#e00020] pl-4" if active else "pl-5"
    with ui.link(target=path).classes(
        f"text-dark no-underline flex flex-nowrap items-center gap-3 w-full pr-4 py-2"
        f" hover:bg-[#efeee9] {style}"
    ) as link:
        ui.icon(icon, color="dark")
        ui.label(label).classes("grow")
    return link


# How often a page looks for something to show as a browser notification.
NOTIFY_SECONDS = 60.0
# Shows browser notifications for new Chat messages (#148): never twice for
# the same message (across tabs, through localStorage), never for the Chat
# open in a visible tab (window.pmpOpenChat, set by the Chat page), and a
# click opens that Chat.
NOTIFY_SCRIPT = """<script>
window.pmpNotify = function (items) {
  if (!("Notification" in window)) return;
  if (Notification.permission !== "granted") return;
  let last = 0;
  try {
    last = Number(localStorage.getItem("pmpLastNotified") || 0);
  } catch (e) {}
  for (const item of items) {
    if (item.id <= last) continue;
    last = Math.max(last, item.id);
    const visible = document.visibilityState === "visible";
    if (visible && window.pmpOpenChat === item.project) continue;
    const shown = new Notification(item.title, {
      body: item.body,
      tag: "pmp-chat-" + item.id,
    });
    shown.onclick = function () {
      window.focus();
      window.location.href = item.url;
      shown.close();
    };
  }
  try {
    localStorage.setItem("pmpLastNotified", String(last));
  } catch (e) {}
};
</script>"""


def notification_items(chat: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """What pmpNotify shows for new Chat messages."""
    return [
        {
            "id": message["message_id"],
            "project": message["project_id"],
            "title": f"{message['author']} in {message['project_title']}",
            "body": ("@ " if message["mentions_me"] else "") + message["text"],
            "url": f"/chats/{message['project_id']}",
        }
        for message in chat
    ]


def _browser_notifications() -> None:
    """Every minute, show new Chat messages as Windows/Mac notifications, when
    the browser allows them (#148)."""
    ui.add_body_html(NOTIFY_SCRIPT)
    seen: dict[str, int | None] = {"since": None}

    async def look() -> None:
        try:
            found = await api.notifications(token(), seen["since"])
        except api.ApiError:
            return
        seen["since"] = found["latest"]
        items = notification_items(found["chat"])
        if items:
            ui.run_javascript(
                f"window.pmpNotify && window.pmpNotify({json.dumps(items)})"
            )

    ui.timer(0.5, look, once=True)
    ui.timer(NOTIFY_SECONDS, look)


def _unread_badge(link: ui.link, *, hide_without_chat: bool) -> None:
    """The number of Unread messages on the Chat item, refreshed every few
    seconds; hidden while there are none."""
    with link:
        badge = ui.badge(color="primary").props("rounded").mark("chat-badge")
        # Red @ while an Unread message mentions the User.
        mentioned = (
            ui.badge("@", color="primary").props("rounded outline").mark("chat-mention")
        )
    badge.set_visibility(False)
    mentioned.set_visibility(False)
    if hide_without_chat:
        link.set_visibility(False)

    async def refresh() -> None:
        try:
            unread = await api.chat_unread(token())
        except api.ApiError:
            return
        badge.text = str(unread["count"])
        badge.set_visibility(unread["count"] > 0)
        mentioned.set_visibility(unread["mentioned"])
        if hide_without_chat:
            link.set_visibility(unread["has_chat"])

    ui.timer(0.1, refresh, once=True)
    ui.timer(BADGE_SECONDS, refresh)


def page_frame(title: str, user: api.CurrentUser):
    """The frame of a logged-in page: navigation, and the logo leading home."""
    # Until the Temporary password is changed, there is nowhere else to go.
    logo_target = None if user.must_change_password else home(user)
    return frame(title, navigation=lambda: navigation(user), home=logo_target)


class ErrorMessage:
    """A hidden error line, shown with `show(text)`."""

    def __init__(self) -> None:
        with ui.row().classes("items-center gap-2") as self._row:
            ui.icon("error", color="primary")
            self._label = ui.label()
        self._row.set_visibility(False)

    def show(self, text: str) -> None:
        self._label.text = text
        self._row.set_visibility(True)

    def hide(self) -> None:
        self._row.set_visibility(False)


def role_page(
    path: str, title: str, roles: set[str]
) -> Callable[[Callable[[api.CurrentUser], Awaitable[None]]], None]:
    """Register a page that only `roles` may see; others get a "no access" message."""

    def register(build: Callable[[api.CurrentUser], Awaitable[None]]) -> None:
        @ui.page(path)
        async def page() -> Response | None:
            user = await guard()
            if isinstance(user, Response):
                return user
            with page_frame(title, user):
                if user.role not in roles:
                    no_access()
                else:
                    await build(user)
            return None

    return register


def _comparable(value: Any) -> Any:
    """A field value as it would be saved: empty is empty, spaces around text
    and the order of a multiple choice don't matter."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return sorted(value)
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


class SaveButton:
    """A Save button that is greyed out while the form shows what was saved,
    and active as soon as a field differs (#121). Call `saved()` after a
    successful save."""

    def __init__(
        self,
        fields: list[ValueElement],
        on_click: Callable[[], Awaitable[None]],
        label: str = "Save",
    ) -> None:
        self._fields = fields
        self.button = ui.button(label, on_click=on_click)
        self.saved()
        for field in fields:
            field.on_value_change(self._check)

    def _values(self) -> list[Any]:
        return [_comparable(field.value) for field in self._fields]

    def saved(self) -> None:
        """What the fields show now is what is saved."""
        self._saved = self._values()
        self._check()

    def _check(self) -> None:
        self.button.set_enabled(self._values() != self._saved)


async def confirm(message: str, action: str) -> bool:
    """Ask before a destructive step; True when the User confirms `action`."""
    with ui.dialog() as dialog, ui.card():
        ui.label(message)
        with ui.row():
            ui.button(action, on_click=lambda: dialog.submit(True)).mark("confirm")
            ui.button("Cancel", on_click=lambda: dialog.submit(False)).props(
                "flat color=dark"
            )
    result = await dialog
    dialog.delete()
    return bool(result)


def no_access() -> None:
    ui.label("No access").classes("text-h4")
    ui.label("You don't have access to this page.")
