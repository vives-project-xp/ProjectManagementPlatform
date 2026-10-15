"""Project Trello boards (spec #61): the board card on a Project's page, and
"Create Trello boards for all Projects"."""

from typing import Any

from nicegui import ui

from pmp_frontend import api
from pmp_frontend.repos import show_results
from pmp_frontend.shell import confirm, token


def trello_card(project: dict[str, Any]) -> None:
    """The board's link once it exists; until then how it gets one."""
    with ui.card().classes("w-full max-w-lg").mark("trello-card"):
        ui.label("Trello board").classes("text-h6")
        if project["trello_board_url"]:
            url = project["trello_board_url"]
            ui.link(url, url, new_tab=True).mark("trello-link")
        elif project["status"] == "archived":
            ui.label("No Trello board.")
        else:
            ui.label(
                'Created with "Create Trello boards for all Projects" on the '
                "Projects screen, once the Project has Members."
            ).classes("text-caption")


async def trello_buttons(after) -> None:
    """ "Create Trello boards for all Projects", or why it is missing; `after`
    reloads the Projects table."""
    status = await api.trello_status(token())
    if not status["connected"]:
        ui.label("Trello isn't connected.").classes("text-caption").mark(
            "trello-not-connected"
        )
        return

    async def create() -> None:
        active = await api.list_projects(token(), status="active")
        waiting = [p for p in active if p["member_count"] and not p["trello_board_url"]]
        if not waiting:
            ui.notify("Every Active Project with Members already has a Trello board.")
            return
        count = len(waiting)
        question = (
            f"Create Trello boards for {count} Project{'s' if count != 1 else ''}?"
        )
        if not await confirm(question, "Create"):
            return
        try:
            results = await api.create_trello_boards(token())
        except api.ApiError as problem:
            ui.notify(problem.message, type="negative")
            return
        show_results(
            "Trello boards",
            [
                (
                    f"{r['title']}: {r['message']}"
                    if r["created"]
                    else f"{r['title']}: Failed. {r['message']}",
                    r["created"],
                )
                for r in results
            ],
        )
        await after()

    ui.button("Create Trello boards for all Projects", on_click=create).props(
        "outline color=dark"
    ).mark("create-trello-boards")
