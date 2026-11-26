from fastapi.responses import RedirectResponse
from nicegui import app, ui
from starlette.responses import Response

from pmp_frontend import (
    api,
    chat_page,
    members_page,
    my_project_page,
    my_projects_page,
    photos,
    planning,
    programmes_page,
    projects_page,
    review_page,
    scheduled_page,
    slideshow_card,
    social_page,
    top3_page,
    users_page,
    vives_login,
    vives_login_page,
)
from pmp_frontend.github_username import github_username_card
from pmp_frontend.shell import (
    TOKEN_KEY,
    ErrorMessage,
    guard,
    home,
    page_frame,
    token,
)
from pmp_frontend.theme import frame


def _notifications_card(user: api.CurrentUser) -> None:
    """Browser notifications (#148): allow them in this browser, and the
    switch for Chat messages."""

    async def allow() -> None:
        answer = await ui.run_javascript(
            "('Notification' in window)"
            " ? Notification.requestPermission() : 'unsupported'",
            timeout=60,
        )
        state.text = PERMISSION.get(answer, PERMISSION["default"])

    async def change(event) -> None:
        try:
            await api.set_notifications(token(), chat_notifications=event.value)
        except api.ApiError as error:
            ui.notify(error.message, type="negative")
            return
        ui.notify(
            "You'll get a notification for new chat messages."
            if event.value
            else "No more notifications for chat messages."
        )

    with ui.card().classes("w-full max-w-md").mark("notifications-card"):
        ui.label("Notifications").classes("text-h6")
        ui.label(
            "A Windows or Mac notification for new messages in your chats, while "
            "a tab of this site is open (also in the background)."
        ).classes("text-caption")
        ui.button(
            "Allow notifications in this browser", icon="notifications", on_click=allow
        ).props("outline color=dark").mark("allow-notifications")
        state = ui.label().classes("text-caption").mark("notification-permission")
        ui.switch(
            "Chat notifications", value=user.chat_notifications, on_change=change
        ).mark("chat-notifications")


PERMISSION = {
    "granted": "This browser shows notifications.",
    "denied": "This browser blocks notifications: allow them in the site settings "
    "(the icon left of the address).",
    "unsupported": "This browser can't show notifications.",
    "default": "Notifications aren't allowed yet.",
}


def _daily_email_card(on: bool) -> None:
    """The switch for the 08:30 Daily email (spec #68)."""

    async def change(event) -> None:
        try:
            await api.set_daily_email(token(), event.value)
        except api.ApiError as error:
            ui.notify(error.message, type="negative")
            return
        ui.notify(
            "You'll get the daily email." if event.value else "No more daily emails."
        )

    with ui.card().classes("w-full max-w-md"):
        ui.label("Daily email").classes("text-h6")
        ui.switch(
            "Email me at 08:30 on days with deadlines or meetings",
            value=on,
            on_change=change,
        ).mark("daily-email")


def register_pages() -> None:
    @ui.page("/")
    async def start_page() -> Response:
        user = await guard()
        if isinstance(user, Response):
            return user
        return RedirectResponse(home(user))

    @ui.page("/login")
    async def login_page(expired: bool = False) -> None:
        def enter(new_token: str, user: api.CurrentUser) -> None:
            app.storage.user[TOKEN_KEY] = new_token
            ui.navigate.to("/account" if user.must_change_password else home(user))

        async def submit() -> None:
            try:
                new_token, user = await api.login(email.value, password.value)
            except api.ApiError as error:
                error_message.show(error.message)
                return
            enter(new_token, user)

        async def submit_dev_login() -> None:
            if dev_user.value is None:
                dev_error.show("Choose a User.")
                return
            try:
                new_token, user = await api.dev_login(dev_user.value)
            except api.ApiError as error:
                dev_error.show(error.message)
                return
            enter(new_token, user)

        vives = await api.vives_start()
        # VIVES login on (#163): nothing else to log in with on the site.
        vives_on = bool(vives and vives.get("configured"))
        dev_users = None if vives_on else await api.dev_login_users()

        # Everything centered on the page (#108).
        with frame("Log in"), ui.column().classes("w-full items-center gap-6 pt-8"):
            with ui.column().classes("items-center gap-1 text-center"):
                ui.label("Project Management Platform").classes("text-h4")
                ui.label("VIVES Project Experience").classes("text-subtitle1")
            if expired:
                ui.label("Your session has expired. Please log in again.")
            vives_login.login_card(vives)
            if vives_on:
                return
            with ui.card().classes("w-full max-w-md"):
                ui.label("Log in").classes("text-h6")
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
                ui.button("Log in", on_click=submit).classes("w-full").mark("log-in")
            if dev_users:
                with ui.card().classes("w-full max-w-md"):
                    ui.label("Test login").classes("text-h6")
                    ui.label(
                        "Turned on for testing: anyone can log in as any User "
                        "without a password. Turn it off before real use."
                    ).classes("text-negative")
                    dev_user = (
                        ui.select(
                            {
                                person["id"]: f"{person['name']} "
                                f"({person['role'].capitalize()})"
                                for person in dev_users
                            },
                            label="User",
                        )
                        .classes("w-full")
                        .mark("dev-login-user")
                    )
                    dev_error = ErrorMessage()
                    ui.button("Log in as this User", on_click=submit_dev_login).mark(
                        "dev-log-in"
                    )

    @ui.page("/change-password")
    def old_change_password_page() -> Response:
        # The page was renamed to My account (spec #49); old links keep working.
        return RedirectResponse("/account")

    @ui.page("/account")
    async def account_page() -> Response | None:
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

        vives = await api.vives_start()
        vives_on = bool(vives and vives.get("configured"))
        with page_frame("My account", user):
            ui.label("My account").classes("text-h4")
            if not vives_on:
                ui.label("Change your password").classes("text-h6")
            if user.must_change_password and not vives_on:
                ui.label("Choose a new password of your own before you continue.")
            with ui.card().classes("w-full max-w-md") as password_card:
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
            # The password lives in Authentik once VIVES login is on (#163).
            password_card.set_visibility(not vives_on)
            # GitHub needs a password of your own first, like everything else;
            # Clients have no GitHub username and no Daily email (spec #132).
            if not user.must_change_password and user.role != "client":
                github_username_card(
                    user.github_username,
                    lambda username: api.set_my_github_username(token(), username),
                )
            if not user.must_change_password:
                _notifications_card(user)
            # The Superuser is on no Project, so never gets the Daily email.
            if not user.must_change_password and user.role not in (
                "superuser",
                "client",
            ):
                _daily_email_card(user.daily_email)
        return None

    users_page.register()
    vives_login.register()
    vives_login_page.register()
    my_projects_page.register()
    projects_page.register()
    members_page.register()
    my_project_page.register()
    programmes_page.register()
    photos.register()
    top3_page.register()
    planning.register()
    social_page.register()
    review_page.register()
    scheduled_page.register()
    slideshow_card.register()
    chat_page.register()
