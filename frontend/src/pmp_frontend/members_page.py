"""The Members screen: every Student and their Project, to complete the teams
(Teachers and the Superuser; read-only)."""

from typing import Any

from nicegui import ui

from pmp_frontend import api
from pmp_frontend.shell import role_page, token
from pmp_frontend.users_page import YEARS

ALL = ""

COLUMNS = [
    {
        "name": "name",
        "label": "Name",
        "field": "name",
        "sortable": True,
        "align": "left",
    },
    {"name": "programme", "label": "Programme", "field": "programme", "align": "left"},
    {
        "name": "year",
        "label": "Year",
        "field": "year",
        "sortable": True,
        "align": "left",
    },
    {"name": "project", "label": "Project", "field": "project", "align": "left"},
]


def _row(student: dict[str, Any]) -> dict[str, Any]:
    suffix = "" if student["is_active"] else " (deactivated)"
    project = student["project"]
    return {
        "id": student["id"],
        "name": f"{student['name']}{suffix}",
        "programme": student["programme"],
        "year": student["year"],
        "project": project["title"] if project else "No Project yet",
    }


def register() -> None:
    @role_page("/members", "Members", {"superuser", "teacher"})
    async def members_page(user: api.CurrentUser) -> None:
        programmes = await api.programmes(token())

        async def refresh() -> None:
            found = await api.students(
                token(),
                without_project=without_project.value,
                programme=programme.value or None,
                year=year.value or None,
            )
            table.rows = [_row(student) for student in found]

        ui.label("Members").classes("text-h4")
        with ui.row().classes("items-center gap-4"):
            without_project = ui.checkbox("No Project yet", on_change=refresh)
            without_project.mark("without-project")
            programme = ui.select(
                {ALL: "All"} | {name: name for name in programmes},
                value=ALL,
                label="Programme",
                on_change=refresh,
            ).classes("w-48")
            programme.mark("programme-filter")
            year = ui.select(
                {ALL: "All"} | {name: name for name in YEARS},
                value=ALL,
                label="Year",
                on_change=refresh,
            ).classes("w-40")
            year.mark("year-filter")
        table = ui.table(columns=COLUMNS, rows=[], row_key="id").classes("w-full")
        table.mark("students")
        await refresh()
