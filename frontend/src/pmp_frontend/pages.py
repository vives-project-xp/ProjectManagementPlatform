from contextlib import suppress

from fastapi.responses import RedirectResponse
from nicegui import app, ui
from starlette.responses import Response

from pmp_frontend import api
from pmp_frontend.theme import frame

TOKEN_KEY = "token"

# The screens each Role sees, in navigation order; the first is the Role's home page.
NAVIGATION: dict[str, list[tuple[str, str]]] = {
    "superuser": [
        ("Users", "/users"),
        ("Projects", "/projects"),
        ("Members", "/members"),
    ],
    "teacher": [("Projects", "/projects"), ("Members", "/members")],
    "student": [("My project", "/my-project")],
}


def _home(user: api.CurrentUser) -> str:
    return NAVIGATION[user.role][0][1]


async def _guard(
    *, allow_temporary_password: bool = False
) -> api.CurrentUser | Response:
    """The logged-in User, or the redirect that sends them where they must go first."""
    token = app.storage.user.get(TOKEN_KEY)
    if not token:
        return RedirectResponse("/login")
    try:
        user = await api.me(token)
    except api.ApiError as error:
        if error.is_unauthorized:
            app.storage.user.pop(TOKEN_KEY, None)
            return RedirectResponse("/login?expired=true")
        # Backend unreachable: the login page shows the system status.
        return RedirectResponse("/login")
    if user.must_change_password and not allow_temporary_password:
        return RedirectResponse("/change-password")
    return user


async def _logout() -> None:
    token = app.storage.user.pop(TOKEN_KEY, None)
    if token:
        # Forgetting the token is what logs out; a failing call changes nothing.
        with suppress(api.ApiError):
            await api.logout(token)
    ui.navigate.to("/login")


def _header(user: api.CurrentUser) -> None:
    with ui.row().classes("items-center gap-4"):
        # Until the Temporary password is changed, there is nowhere else to go.
        if not user.must_change_password:
            for label, path in NAVIGATION[user.role]:
                ui.link(label, path).classes("text-dark")
            ui.link("Change password", "/change-password").classes("text-dark")
        ui.label(user.full_name).classes("font-medium")
        ui.button("Log out", on_click=_logout).props("flat color=dark")


def _error_message() -> ui.label:
    """A hidden error line; set its text and make it visible to show a problem."""
    with ui.row().classes("items-center gap-2") as row:
        ui.icon("error", color="primary")
        label = ui.label()
    label.bind_visibility_to(row)
    label.set_visibility(False)
    return label


def _status_label(name: str, online: bool) -> None:
    # Text stays black (house style); only the icon signals status, in VIVES red
    # when something is offline.
    with ui.row().classes("items-center gap-2"):
        if online:
            ui.icon("check_circle", color="dark")
        else:
            ui.icon("error", color="primary")
        ui.label(f"{name}: {'online' if online else 'offline'}")


def _placeholder_page(path: str, title: str, roles: set[str], text: str) -> None:
    @ui.page(path)
    async def page() -> Response | None:
        user = await _guard()
        if isinstance(user, Response):
            return user
        with frame(title, header=lambda: _header(user)):
            if user.role not in roles:
                ui.label("No access").classes("text-h4")
                ui.label("You don't have access to this page.")
                return None
            ui.label(title).classes("text-h4")
            ui.label(text)
        return None


def register_pages() -> None:
    @ui.page("/")
    async def start_page() -> Response:
        user = await _guard()
        if isinstance(user, Response):
            return user
        return RedirectResponse(_home(user))

    @ui.page("/login")
    async def login_page(expired: bool = False) -> None:
        async def submit() -> None:
            try:
                token, user = await api.login(email.value, password.value)
            except api.ApiError as error:
                error_message.text = error.message
                error_message.set_visibility(True)
                return
            app.storage.user[TOKEN_KEY] = token
            ui.navigate.to(
                "/change-password" if user.must_change_password else _home(user)
            )

        with frame("Log in"):
            ui.label("Project Management Platform").classes("text-h4")
            ui.label("VIVES Project Experience").classes("text-subtitle1")
            with ui.card().classes("w-full max-w-md"):
                ui.label("Log in").classes("text-h6")
                if expired:
                    ui.label("Your session has expired. Please log in again.")
                email = (
                    ui.input("Email")
                    .props("type=email")
                    .classes("w-full")
                    .mark("email")
                )
                password = (
                    ui.input("Password", password=True)
                    .classes("w-full")
                    .mark("password")
                    .on("keydown.enter", submit)
                )
                error_message = _error_message()
                ui.button("Log in", on_click=submit).mark("log-in")
            health = await api.get_health()
            with ui.card().classes("w-full"):
                ui.label("System status").classes("text-h6")
                _status_label("Backend", health.backend_online)
                _status_label("Database", health.database_online)

    @ui.page("/change-password")
    async def change_password_page() -> Response | None:
        user = await _guard(allow_temporary_password=True)
        if isinstance(user, Response):
            return user

        async def submit() -> None:
            if new.value != repeat.value:
                error_message.text = "The new passwords do not match."
                error_message.set_visibility(True)
                return
            try:
                await api.change_password(
                    app.storage.user.get(TOKEN_KEY, ""), current.value, new.value
                )
            except api.ApiError as error:
                if error.is_unauthorized:
                    ui.navigate.to("/login?expired=true")
                    return
                error_message.text = error.message
                error_message.set_visibility(True)
                return
            ui.notify("Your password has been changed.")
            ui.navigate.to(_home(user))

        with frame("Change password", header=lambda: _header(user)):
            ui.label("Change your password").classes("text-h4")
            if user.must_change_password:
                ui.label("Choose a new password of your own before you continue.")
            with ui.card().classes("w-full max-w-md"):
                current = (
                    ui.input("Current password", password=True)
                    .classes("w-full")
                    .mark("current-password")
                )
                new = (
                    ui.input("New password (at least 8 characters)", password=True)
                    .classes("w-full")
                    .mark("new-password")
                )
                repeat = (
                    ui.input("Repeat new password", password=True)
                    .classes("w-full")
                    .mark("repeat-password")
                )
                error_message = _error_message()
                ui.button("Change password", on_click=submit).mark("change-password")
        return None

    # Placeholder screens; later tickets fill them in.
    _placeholder_page(
        "/users", "Users", {"superuser"}, "Managing Users comes in a later version."
    )
    _placeholder_page(
        "/projects",
        "Projects",
        {"superuser", "teacher"},
        "Managing Projects comes in a later version.",
    )
    _placeholder_page(
        "/members",
        "Members",
        {"superuser", "teacher"},
        "Managing Members comes in a later version.",
    )
    _placeholder_page(
        "/my-project",
        "My project",
        {"student"},
        "Your Project will be shown here.",
    )
