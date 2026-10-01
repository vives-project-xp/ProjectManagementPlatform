"""The Projects screen and a Project's details page (Teachers and the Superuser)."""

from collections.abc import Callable
from typing import Any

from nicegui import ui
from starlette.responses import Response

from pmp_frontend import api
from pmp_frontend.shell import ErrorMessage, guard, header, no_access, role_page, token
from pmp_frontend.theme import frame

STAFF = {"superuser", "teacher"}

COLUMNS = [
    {
        "name": "title",
        "label": "Title",
        "field": "title",
        "sortable": True,
        "align": "left",
    },
    {"name": "owner", "label": "Product Owner", "field": "owner", "align": "left"},
    {"name": "team_size", "label": "Team size", "field": "team_size", "align": "left"},
    {"name": "status", "label": "Status", "field": "status", "align": "left"},
]


def _row(project: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": project["id"],
        "title": project["title"],
        "owner": project["product_owner"]["name"],
        "team_size": f"{project['team_size_min']}–{project['team_size_max']}",
        "status": project["status"].capitalize(),
    }


def _project_form(
    teachers: list[dict[str, Any]], project: dict[str, Any] | None = None
) -> Callable[[], dict[str, Any]]:
    """The Project fields, filled from `project`; returns a function reading them."""
    project = project or {}
    title = ui.input("Title", value=project.get("title", "")).classes("w-full")
    title.mark("title")
    description = ui.textarea(
        "Description (optional)", value=project.get("description") or ""
    ).classes("w-full")
    description.mark("description")
    owner = ui.select(
        {teacher["id"]: teacher["name"] for teacher in teachers},
        label="Product Owner",
        value=project.get("product_owner", {}).get("id"),
    ).classes("w-full")
    owner.mark("product-owner")
    with ui.row().classes("w-full"):
        minimum = ui.number(
            "Minimum Team size", value=project.get("team_size_min"), min=1, format="%d"
        ).mark("team-size-min")
        maximum = ui.number(
            "Maximum Team size", value=project.get("team_size_max"), min=1, format="%d"
        ).mark("team-size-max")

    def read() -> dict[str, Any]:
        return {
            "title": title.value,
            "description": description.value or None,
            "product_owner_id": owner.value,
            "team_size_min": int(minimum.value) if minimum.value is not None else None,
            "team_size_max": int(maximum.value) if maximum.value is not None else None,
        }

    return read


def register() -> None:
    @role_page("/projects", "Projects", STAFF)
    async def projects_page(user: api.CurrentUser) -> None:
        teachers = await api.teachers(token())

        async def refresh() -> None:
            table.rows = [_row(project) for project in await api.list_projects(token())]

        async def create() -> None:
            try:
                created = await api.create_project(token(), read_fields())
            except api.ApiError as error:
                error_message.show(error.message)
                return
            dialog.close()
            ui.notify(f"Project {created['title']} was created.")
            await refresh()

        with ui.dialog() as dialog, ui.card().classes("w-full max-w-lg"):
            ui.label("New Project").classes("text-h6")
            read_fields = _project_form(teachers)
            error_message = ErrorMessage()
            with ui.row():
                ui.button("Create", on_click=create).mark("create-project")
                ui.button("Cancel", on_click=dialog.close).props("flat color=dark")

        with ui.row().classes("w-full items-center"):
            ui.label("Projects").classes("text-h4")
            ui.space()
            ui.button("New Project", on_click=dialog.open).mark("new-project")
        table = ui.table(columns=COLUMNS, rows=[], row_key="id").classes("w-full")
        table.mark("projects")
        table.on(
            "rowClick", lambda event: ui.navigate.to(f"/projects/{event.args[1]['id']}")
        )
        await refresh()

    @ui.page("/projects/{project_id}")
    async def project_details(project_id: int) -> Response | None:
        user = await guard()
        if isinstance(user, Response):
            return user
        with frame("Project", header=lambda: header(user)):
            if user.role not in STAFF:
                no_access()
                return None
            try:
                project = await api.get_project(token(), project_id)
            except api.ApiError as error:
                ui.label(error.message)
                return None
            teachers = await api.teachers(token())

            async def save() -> None:
                try:
                    saved = await api.update_project(token(), project_id, read_fields())
                except api.ApiError as error:
                    error_message.show(error.message)
                    return
                error_message.hide()
                heading.text = saved["title"]
                ui.notify("The changes were saved.")

            ui.link("← Projects", "/projects").classes("text-dark")
            heading = ui.label(project["title"]).classes("text-h4")
            ui.label(f"Status: {project['status'].capitalize()}")
            with ui.card().classes("w-full max-w-lg"):
                read_fields = _project_form(teachers, project)
                error_message = ErrorMessage()
                ui.button("Save", on_click=save).mark("save-project")
        return None
