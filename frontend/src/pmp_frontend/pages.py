from fastapi.responses import RedirectResponse
from nicegui import app, ui
from starlette.responses import Response

from pmp_frontend import (
    api,
    members_page,
    my_project_page,
    projects_page,
    users_page,
)
from pmp_frontend.shell import (
    TOKEN_KEY,
    ErrorMessage,
    guard,
    home,
    page_frame,
    token,
)
from pmp_frontend.theme import frame


def register_pages() -> None:
    @ui.page("/")
    async def start_page() -> Response:
        user = await guard()
        if isinstance(user, Response):
            return user
        return RedirectResponse(home(user))

    @ui.page("/login")
    async def login_page(expired: bool = False) -> None:
        async def submit() -> None:
            try:
                new_token, user = await api.login(email.value, password.value)
            except api.ApiError as error:
                error_message.show(error.message)
                return
            app.storage.user[TOKEN_KEY] = new_token
            ui.navigate.to(
                "/change-password" if user.must_change_password else home(user)
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
                error_message = ErrorMessage()
                ui.button("Log in", on_click=submit).mark("log-in")

    @ui.page("/change-password")
    async def change_password_page() -> Response | None:
        user = await guard(allow_temporary_password=True)
        if isinstance(user, Response):
            return user

        async def submit() -> None:
            if new.value != repeat.value:
                error_message.show("The new passwords do not match.")
                return
            try:
                await api.change_password(token(), current.value, new.value)
            except api.ApiError as error:
                if error.is_unauthorized:
                    ui.navigate.to("/login?expired=true")
                    return
                error_message.show(error.message)
                return
            ui.notify("Your password has been changed.")
            ui.navigate.to(home(user))

        with page_frame("Change password", user):
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
                error_message = ErrorMessage()
                ui.button("Change password", on_click=submit).mark("change-password")
        return None

    users_page.register()
    projects_page.register()
    members_page.register()
    my_project_page.register()
