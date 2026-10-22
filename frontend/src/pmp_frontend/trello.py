"""Project Trello boards (spec #61): the board card on a Project's page and on a
Student's My project, and "Create Trello boards for all Projects" / "Check all
Trello members"."""

from typing import Any

from nicegui import ui

from pmp_frontend import api
from pmp_frontend.repos import show_results
from pmp_frontend.shell import ErrorMessage, confirm, token

SIGN_UP_URL = "https://trello.com/signup"


def _status_text(person: dict[str, Any]) -> str:
    return {
        "has_access": "Has access",
        "invited": f"Invited: sign up on Trello with {person['email']}",
        "not_invited": "Not invited yet: press Check members",
    }[person["status"]]


async def _access_list(project_id: int) -> None:
    """Each person's status, read live from Trello."""
    try:
        access = await api.board_access(token(), project_id)
    except api.ApiError as problem:
        ui.label(problem.message).classes("text-negative")
        return
    for person in access["people"]:
        ui.label(f"{person['name']} ({person['role']}): {_status_text(person)}").mark(
            f"trello-{person['status']}"
        )


async def trello_card(project: dict[str, Any], *, editable: bool) -> None:
    """The board's link, who has access and "Check members" once it exists;
    until then how it gets one."""

    async def check() -> None:
        try:
            result = await api.check_trello_members(token(), project["id"])
        except api.ApiError as problem:
            error.show(problem.message)
            return
        error.hide()
        ui.notify(result["message"])
        if result["board_gone"]:
            ui.navigate.to(f"/projects/{project['id']}")
            return
        access.refresh()

    @ui.refreshable
    async def access() -> None:
        await _access_list(project["id"])

    with ui.card().classes("w-full max-w-lg").mark("trello-card"):
        ui.label("Trello board").classes("text-h6")
        error = ErrorMessage()
        if project["trello_board_url"]:
            url = project["trello_board_url"]
            ui.link(url, url, new_tab=True).mark("trello-link")
            if editable:
                await access()
                ui.button("Check members", on_click=check).props(
                    "outline color=dark"
                ).mark("check-trello-members")
        elif not editable:
            ui.label("No Trello board.")
        else:
            ui.label(
                'Created with "Create Trello boards for all Projects" on the '
                "Projects screen, once the Project has Members."
            ).classes("text-caption")


async def trello_buttons(after) -> None:
    """A "Trello" menu with "Create Trello boards for all Projects" and "Check all
    Trello members", or why it is missing; `after` reloads the Projects table."""
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

    async def check_all() -> None:
        question = (
            "Check the members of every Trello board? Missing people are invited, "
            "and people who left are removed."
        )
        if not await confirm(question, "Check"):
            return
        try:
            results = await api.check_all_trello_members(token())
        except api.ApiError as problem:
            ui.notify(problem.message, type="negative")
            return
        show_results(
            "Trello members checked",
            [
                (f"{r['title']}: {r['message']}", not r["message"].startswith("Failed"))
                for r in results
            ],
        )
        await after()

    with (
        ui.dropdown_button("Trello", icon="view_kanban")
        .props("outline color=dark no-caps")
        .mark("trello-menu")
    ):
        ui.item("Create Trello boards for all Projects", on_click=create).mark(
            "create-trello-boards"
        )
        ui.item("Check all Trello members", on_click=check_all).mark(
            "check-all-trello-members"
        )


async def my_trello_card() -> None:
    """On My project: the Student's Trello board and their next step."""
    try:
        mine = await api.my_trello_board(token())
    except api.ApiError as problem:
        ui.label(problem.message).classes("text-negative")
        return
    if mine["board_url"] is None:
        return
    with ui.card().classes("w-full").mark("my-trello-board"):
        ui.label("Trello board").classes("text-h6")
        ui.link(mine["board_url"], mine["board_url"], new_tab=True)
        if mine["status"] == "invited":
            ui.link(
                f"Sign up on Trello with {mine['email']} to get access",
                SIGN_UP_URL,
                new_tab=True,
            ).mark("trello-sign-up")
        elif mine["status"] == "has_access":
            ui.label("You have access.").mark("trello-has_access")
        else:
            ui.label(
                "You'll be invited soon: your Product Owner still has to check "
                "the members."
            ).mark("trello-not_invited")
