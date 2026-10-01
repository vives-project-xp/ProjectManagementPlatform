"""My project: a Student's own Project, its Product Owner and fellow Members."""

from nicegui import ui

from pmp_frontend import api
from pmp_frontend.shell import role_page, token


def register() -> None:
    @role_page("/my-project", "My project", {"student"})
    async def my_project_page(user: api.CurrentUser) -> None:
        ui.label("My project").classes("text-h4")
        project = await api.my_project(token())
        if project is None:
            ui.label("You haven't been assigned to a project yet.")
            return
        with ui.card().classes("w-full"):
            ui.label(project["title"]).classes("text-h5").mark("project-title")
            if project["description"]:
                ui.label(project["description"])
            ui.label(f"Product Owner: {project['product_owner']}")
        with ui.card().classes("w-full"):
            ui.label("Fellow Members").classes("text-h6")
            if project["fellow_members"]:
                for name in project["fellow_members"]:
                    ui.label(name)
            else:
                ui.label("You are the only Member so far.")
