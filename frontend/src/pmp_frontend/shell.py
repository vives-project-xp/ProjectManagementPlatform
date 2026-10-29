"""What every logged-in page shares: the session, the page guard and the header."""

from collections.abc import Awaitable, Callable
from contextlib import suppress

from fastapi.responses import RedirectResponse
from nicegui import app, ui
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
    ],
    "teacher": [
        ("Projects", "/projects", "folder"),
        ("Members", "/members", "badge"),
        ("Top 3", "/top3", "format_list_numbered"),
        ("Planning", "/planning", "event"),
        ("Chats", "/chats", "forum"),
    ],
    "student": [("My project", "/my-project", "work"), ("Chat", "/chat", "chat")],
}
# The navigation items that show the Unread badge (spec #91), and how often it
# is refreshed.
CHAT_PATHS = {"/chat", "/chats"}
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


def header(user: api.CurrentUser) -> None:
    with ui.row().classes("items-center gap-4"):
        # Until the Temporary password is changed, there is nowhere else to go.
        if not user.must_change_password:
            for label, path, icon in NAVIGATION[user.role]:
                link = _navigation_link(label, path, icon).mark("navigation")
                if path in CHAT_PATHS:
                    # A Student without any Chat doesn't get the item at all.
                    _unread_badge(link, hide_without_chat=user.role == "student")
            _navigation_link("My account", "/account", "account_circle")
        ui.label(user.full_name).classes("font-medium")
        ui.button("Log out", icon="logout", on_click=_logout).props("flat color=dark")


def _navigation_link(label: str, path: str, icon: str) -> ui.link:
    # Icons stay black like the text (house style), always next to the label.
    with ui.link(target=path).classes(
        "text-dark no-underline flex items-center gap-1"
    ) as link:
        ui.icon(icon, color="dark")
        ui.label(label)
    return link


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
    return frame(title, header=lambda: header(user), home=logo_target)


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
