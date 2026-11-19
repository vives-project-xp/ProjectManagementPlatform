"""My projects (spec #132): a Client's home screen with the Projects they
follow. Linking Clients to Projects and the read-only pages come with #134."""

from nicegui import ui

from pmp_frontend import api
from pmp_frontend.shell import role_page

NOTHING_YET = "You don't follow any Projects yet."


def register() -> None:
    @role_page("/my-projects", "My projects", {"client"})
    async def my_projects_page(user: api.CurrentUser) -> None:
        ui.label("My projects").classes("text-h5")
        ui.label(
            "The Projects you follow appear here once a Teacher links you to them."
        ).classes("text-caption")
        ui.label(NOTHING_YET).mark("no-projects")
