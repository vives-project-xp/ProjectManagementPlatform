"""The GitHub username card (spec #49): look the account up, confirm it by its
profile picture and name, then save. Used on My account, My project and, for the
Superuser, on a User's details page."""

from collections.abc import Awaitable, Callable
from typing import Any

from nicegui import ui

from pmp_frontend import api
from pmp_frontend.shell import ErrorMessage, token

Save = Callable[[str | None], Awaitable[dict[str, Any]]]


def github_username_card(current: str | None, save: Save) -> None:
    """`save(username)` stores it (None clears it) and returns the saved User."""

    def show_saved(username: str | None) -> None:
        saved.text = (
            f"Saved: {username}" if username else "No GitHub username saved yet."
        )
        remove_button.set_visibility(username is not None)

    async def check() -> None:
        confirmation.clear()
        try:
            account = await api.github_account(token(), username.value or "")
        except api.ApiError as problem:
            error.show(problem.message)
            return
        error.hide()
        with confirmation:
            ui.image(account["avatar_url"]).classes("w-12 h-12 rounded-full")
            with ui.column().classes("gap-0"):
                ui.label(account["name"] or account["login"]).classes("font-medium")
                ui.label(account["login"]).classes("text-caption")
            ui.button(
                "Yes, save this account",
                on_click=lambda: store(account["login"]),
            ).mark("save-github")

    async def store(login: str | None) -> None:
        try:
            user = await save(login)
        except api.ApiError as problem:
            error.show(problem.message)
            return
        error.hide()
        confirmation.clear()
        username.value = user["github_username"] or ""
        show_saved(user["github_username"])
        ui.notify(
            f"GitHub username {login} was saved."
            if login
            else "The GitHub username was removed."
        )

    with ui.card().classes("w-full max-w-md").mark("github-card"):
        ui.label("GitHub username").classes("text-h6")
        ui.label("Needed to get access to your Project's repository.").classes(
            "text-caption"
        )
        saved = ui.label().mark("github-saved")
        username = ui.input("GitHub username", value=current or "").classes("w-full")
        username.mark("github-username")
        error = ErrorMessage()
        confirmation = ui.row().classes("items-center gap-3")
        with ui.row():
            ui.button("Check", on_click=check).props("outline color=dark").mark(
                "check-github"
            )
            remove_button = (
                ui.button("Remove", on_click=lambda: store(None))
                .props("flat color=dark")
                .mark("remove-github")
            )
        show_saved(current)
