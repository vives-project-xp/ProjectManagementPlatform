"""The Top 3 screen (Teachers and the Superuser): the one Top 3 round (spec #37)."""

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from nicegui import ui

from pmp_frontend import api
from pmp_frontend.shell import ErrorMessage, confirm, role_page, token

STAFF = {"superuser", "teacher"}
# Deadlines are entered and shown in Belgian time.
BRUSSELS = ZoneInfo("Europe/Brussels")


def shown(moment: str) -> str:
    return (
        datetime.fromisoformat(moment).astimezone(BRUSSELS).strftime("%d/%m/%Y %H:%M")
    )


def deadline_from(date_text: str, time_text: str) -> str | None:
    """The ISO deadline for a date and time in Belgian time, or None if unreadable."""
    try:
        local = datetime.fromisoformat(f"{date_text}T{time_text}")
    except ValueError:
        return None
    return local.replace(tzinfo=BRUSSELS).isoformat()


def register() -> None:
    @role_page("/top3", "Top 3", STAFF)
    async def top3_page(user: api.CurrentUser) -> None:
        def show(state: dict[str, Any]) -> None:
            deadline = state["deadline"]
            if deadline is None:
                status.text = "No Top 3 round yet."
                set_button.text = "Open the round"
            elif state["is_open"]:
                status.text = f"Open until {shown(deadline)}"
                set_button.text = "Move the deadline"
            else:
                status.text = f"Closed since {shown(deadline)}"
                set_button.text = "Reopen the round"
            close_button.set_visibility(state["is_open"])
            new_button.set_visibility(deadline is not None)

        def chosen_deadline() -> str | None:
            deadline = deadline_from(date.value or "", time.value or "")
            if deadline is None:
                error.show("Choose a date and a time.")
            return deadline

        async def change(call) -> None:
            try:
                state = await call
            except api.ApiError as problem:
                error.show(problem.message)
                return
            error.hide()
            show(state)

        async def set_deadline() -> None:
            deadline = chosen_deadline()
            if deadline is not None:
                await change(api.set_top3_deadline(token(), deadline))

        async def close() -> None:
            question = "Close the Top 3 round now? Students can no longer submit."
            if await confirm(question, "Close"):
                await change(api.close_top3_round(token()))

        async def start_new() -> None:
            deadline = chosen_deadline()
            if deadline is None:
                return
            question = (
                "Start a new Top 3 round? Every submitted Top 3 is cleared, "
                "for the new semester."
            )
            if await confirm(question, "Start new round"):
                await change(api.start_new_top3_round(token(), deadline))

        ui.label("Top 3").classes("text-h4")
        with ui.card().classes("w-full max-w-lg"):
            ui.label("Top 3 round").classes("text-h6")
            status = ui.label().mark("round-status")
            with ui.row().classes("w-full"):
                date = ui.input("Deadline date").props("type=date stack-label")
                date.mark("deadline-date")
                time = ui.input("Deadline time (Belgian time)", value="23:59")
                time.props("type=time stack-label").mark("deadline-time")
            error = ErrorMessage()
            with ui.row():
                set_button = ui.button(on_click=set_deadline).mark("set-deadline")
                close_button = (
                    ui.button("Close now", on_click=close)
                    .props("outline color=dark")
                    .mark("close-round")
                )
                new_button = (
                    ui.button("Start a new Top 3 round", on_click=start_new)
                    .props("outline color=negative")
                    .mark("new-round")
                )
        show(await api.top3_round(token()))
