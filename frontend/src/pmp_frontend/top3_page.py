"""The Top 3 screen (Teachers and the Superuser): the one Top 3 round (spec #37)."""

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from nicegui import ui

from pmp_frontend import api
from pmp_frontend.projects_page import add_member_moving_if_confirmed
from pmp_frontend.shell import ErrorMessage, confirm, role_page, token
from pmp_frontend.users_page import YEARS

STAFF = {"superuser", "teacher"}
RANKS = ["1st choice", "2nd choice", "3rd choice"]
ALL = ""

SUMMARY_COLUMNS = [
    {"name": "title", "label": "Project", "field": "title", "align": "left"},
    {"name": "first", "label": "1st", "field": "first", "sortable": True},
    {"name": "second", "label": "2nd", "field": "second", "sortable": True},
    {"name": "third", "label": "3rd", "field": "third", "sortable": True},
]
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


def choice_text(choice: dict[str, Any]) -> str:
    """E.g. "1st choice: Drone", marking a Project that can no longer be chosen."""
    title = choice["title"] or "A deleted Project"
    if not choice["available"]:
        title += " (no longer available)"
    return f"{RANKS[choice['rank'] - 1]}: {title}"


def _student_card(student: dict[str, Any], reset, add_to) -> None:
    with ui.card().classes("w-full").mark(f"student-{student['id']}"):
        ui.label(student["name"]).classes("text-subtitle1")
        ui.label(f"{student['programme']}, year {student['year']}").classes(
            "text-caption"
        )
        project = student["project"]
        ui.label(f"Project: {project['title']}" if project else "No Project yet")
        if student["top3"] is None:
            ui.label("Hasn't chosen yet.")
            return
        current = (project or {}).get("id")
        for choice in student["top3"]:
            with ui.row().classes("w-full items-center"):
                ui.label(choice_text(choice))
                if choice["available"] and choice["project_id"] != current:
                    ui.button(
                        f"Add to {choice['title']}",
                        on_click=lambda c=choice: add_to(student, c),
                    ).props("flat dense color=primary").mark(
                        f"add-{student['id']}-to-{choice['project_id']}"
                    )
        ui.label(f"Submitted on {shown(student['submitted_at'])}.").classes(
            "text-caption"
        )
        ui.button("Reset top 3", on_click=lambda: reset(student)).props(
            "outline color=dark"
        ).mark(f"reset-top3-{student['id']}")


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
            await refresh_overview()

        async def refresh_overview() -> None:
            found = await api.top3_overview(
                token(),
                programme=programme.value or None,
                year=year.value or None,
                without_top3=without_top3.value,
            )
            students.clear()
            with students:
                if not found["students"]:
                    ui.label("No Students match these filters.")
                for student in found["students"]:
                    _student_card(student, reset, add_to)
            summary.rows = found["summary"]

        async def add_to(student: dict[str, Any], choice: dict[str, Any]) -> None:
            # The Members rules apply: Team size, moving, Archived Projects.
            try:
                details = await add_member_moving_if_confirmed(
                    choice["project_id"], student["id"]
                )
            except api.ApiError as problem:
                overview_error.show(problem.message)
                return
            if details is None:
                return
            overview_error.hide()
            ui.notify(f"{student['name']} was added to {choice['title']}.")
            await refresh_overview()

        async def reset(student: dict[str, Any]) -> None:
            question = f"Reset the top 3 of {student['name']}? They can choose again."
            if not await confirm(question, "Reset"):
                return
            try:
                await api.reset_top3(token(), student["id"])
            except api.ApiError as problem:
                overview_error.show(problem.message)
                return
            overview_error.hide()
            ui.notify(f"The top 3 of {student['name']} was reset.")
            await refresh_overview()

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

        programmes = await api.programmes(token())
        ui.label("Students").classes("text-h6")
        with ui.row().classes("items-center gap-4"):
            without_top3 = ui.checkbox("Hasn't chosen yet", on_change=refresh_overview)
            without_top3.mark("without-top3")
            programme = ui.select(
                {ALL: "All"} | {name: name for name in programmes},
                value=ALL,
                label="Programme",
                on_change=refresh_overview,
            ).classes("w-48")
            programme.mark("programme-filter")
            year = ui.select(
                {ALL: "All"} | {name: name for name in YEARS},
                value=ALL,
                label="Year",
                on_change=refresh_overview,
            ).classes("w-40")
            year.mark("year-filter")
        overview_error = ErrorMessage()
        students = ui.column().classes("w-full").mark("top3-students")
        ui.label("Per Project").classes("text-h6")
        ui.label("How many Students put each open Project 1st, 2nd and 3rd.")
        summary = ui.table(columns=SUMMARY_COLUMNS, rows=[], row_key="project_id")
        summary.classes("w-full").mark("top3-summary")

        show(await api.top3_round(token()))
        await refresh_overview()
