"""My projects (spec #132, #134): a Client's home screen with the Projects
they follow, and a read-only page per Project."""

from typing import Any

from nicegui import ui
from starlette.responses import Response

from pmp_frontend import api
from pmp_frontend.clients_section import client_label
from pmp_frontend.photos import show_photo
from pmp_frontend.planning import my_planning_card
from pmp_frontend.shell import guard, no_access, page_frame, role_page, token
from pmp_frontend.theme import external_link

NOTHING_YET = "You don't follow any Projects yet."


def _project_link(project: dict[str, Any]) -> None:
    with (
        ui.link(target=f"/my-projects/{project['id']}")
        .classes("text-dark no-underline w-full max-w-lg")
        .mark(f"followed-{project['id']}"),
        ui.card().classes("w-full"),
    ):
        show_photo(project["id"], project["photo_version"])
        ui.label(project["title"]).classes("text-h6")


def _followed_page(project: dict[str, Any]) -> None:
    archived = project["status"] == "archived"
    ui.link("← My projects", "/my-projects").classes("text-dark")
    with ui.card().classes("w-full max-w-2xl"):
        show_photo(project["id"], project["photo_version"])
        ui.label(project["title"]).classes("text-h5")
        if archived:
            ui.label("This Project is archived.").classes("text-caption").mark(
                "archived-note"
            )
        if project["description"]:
            ui.label(project["description"]).classes("whitespace-pre-wrap")
        ui.label(f"Product Owner: {project['product_owner']}")
        if project["repo_url"]:
            name = project["repo_url"].removeprefix("https://github.com/")
            external_link(project["repo_url"], name, "github")
    with ui.card().classes("w-full max-w-2xl").mark("followed-team"):
        ui.label("Team").classes("text-h6")
        if project["members"]:
            for name in project["members"]:
                ui.label(name)
        else:
            ui.label("No Members yet.")
    with ui.card().classes("w-full max-w-2xl").mark("followed-clients"):
        ui.label("Clients").classes("text-h6")
        for person in project["clients"]:
            ui.label(client_label(person))


def register() -> None:
    @role_page("/my-projects", "My projects", {"client"})
    async def my_projects_page(user: api.CurrentUser) -> None:
        ui.label("My projects").classes("text-h5")
        followed = await api.my_projects(token())
        if not followed:
            ui.label(
                "The Projects you follow appear here once a Teacher links you to them."
            ).classes("text-caption")
            ui.label(NOTHING_YET).mark("no-projects")
            return
        active = [p for p in followed if p["status"] == "active"]
        archived = [p for p in followed if p["status"] == "archived"]
        for project in active:
            _project_link(project)
        if archived:
            ui.label("Archived").classes("text-h6")
            for project in archived:
                _project_link(project)

    @ui.page("/my-projects/{project_id}")
    async def followed_project(project_id: int) -> Response | None:
        user = await guard()
        if isinstance(user, Response):
            return user
        with page_frame("My projects", user):
            if user.role != "client":
                no_access()
                return None
            try:
                project = await api.followed_project(token(), project_id)
            except api.ApiError as problem:
                ui.label(problem.message)
                return None
            _followed_page(project)
            with ui.element("div").classes("w-full max-w-2xl"):
                await my_planning_card(
                    lambda: api.followed_planning(token(), project_id)
                )
        return None
