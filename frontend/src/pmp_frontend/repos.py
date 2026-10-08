"""Project repositories on GitHub (spec #49): the repository card on a Project's
page, and "Create repos for all Projects" / "Check all members"."""

from typing import Any

from nicegui import ui

from pmp_frontend import api
from pmp_frontend.shell import ErrorMessage, confirm, token

STATUS_TEXT = {
    "has_access": "Has access",
    "invited": "Invited, not accepted yet",
    "not_invited": "Not invited yet: press Check members",
    "no_username": "No GitHub username yet",
}


async def _access_list(project_id: int) -> None:
    """Each person's access, read live from GitHub."""
    try:
        access = await api.repository_access(token(), project_id)
    except api.ApiError as problem:
        ui.label(problem.message).classes("text-negative")
        return
    for person in access["people"]:
        ui.label(
            f"{person['name']} ({person['role']}): {STATUS_TEXT[person['status']]}"
        ).mark(f"access-{person['status']}")


async def repository_card(project: dict[str, Any], *, editable: bool) -> None:
    """Once the repository exists: its link, who has access and "Check members";
    until then its name, editable."""

    async def save() -> None:
        try:
            saved = await api.set_repo_name(token(), project["id"], name.value or None)
        except api.ApiError as problem:
            error.show(problem.message)
            return
        error.hide()
        name.value = saved["repo_name"]
        ui.notify(f"The repository will be called {saved['repo_name']}.")

    async def check() -> None:
        try:
            result = await api.check_members(token(), project["id"])
        except api.ApiError as problem:
            error.show(problem.message)
            return
        error.hide()
        ui.notify(result["message"])
        if result["repo_gone"]:
            ui.navigate.to(f"/projects/{project['id']}")
            return
        access.refresh()

    @ui.refreshable
    async def access() -> None:
        await _access_list(project["id"])

    with ui.card().classes("w-full max-w-lg").mark("repository-card"):
        ui.label("GitHub repository").classes("text-h6")
        error = ErrorMessage()
        if project["repo_url"]:
            ui.link(project["repo_url"], project["repo_url"], new_tab=True).mark(
                "repo-link"
            )
            if editable:
                await access()
                ui.button("Check members", on_click=check).props(
                    "outline color=dark"
                ).mark("check-members")
            return
        if not editable:
            ui.label("No repository.")
            return
        ui.label(
            'Created with "Create repos for all Projects" on the Projects screen, '
            "once the Project has Members."
        ).classes("text-caption")
        name = ui.input("Repository name", value=project["repo_name"]).classes("w-full")
        name.mark("repo-name")
        ui.button("Save name", on_click=save).props("outline color=dark").mark(
            "save-repo-name"
        )


def _show_results(title: str, lines: list[tuple[str, bool]]) -> None:
    """`lines`: (text, whether it went well)."""
    with ui.dialog() as dialog, ui.card().classes("w-full max-w-lg"):
        ui.label(title).classes("text-h6")
        if not lines:
            ui.label("Nothing to do.")
        for text, ok in lines:
            label = ui.label(text)
            if not ok:
                label.classes("text-negative")
        ui.button("Done", on_click=dialog.close).mark("results-done")
    dialog.open()


async def github_buttons(after) -> None:
    """ "Create repos for all Projects" and "Check all members", or why they are
    missing; `after` reloads the Projects table."""
    status = await api.github_status(token())
    if not status["connected"]:
        ui.label("GitHub isn't connected.").classes("text-caption").mark(
            "github-not-connected"
        )
        return

    async def create() -> None:
        active = await api.list_projects(token(), status="active")
        waiting = [p for p in active if p["member_count"] and not p["repo_url"]]
        if not waiting:
            ui.notify("Every Active Project with Members already has a repository.")
            return
        count = len(waiting)
        question = (
            f"Create repositories for {count} Project{'s' if count != 1 else ''} "
            f"in {status['org']}?"
        )
        if not await confirm(question, "Create"):
            return
        try:
            results = await api.create_repos(token())
        except api.ApiError as problem:
            ui.notify(problem.message, type="negative")
            return
        _show_results(
            "Repositories",
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
            "Check the members of every repository? Missing people are invited, "
            "and people who left lose their access."
        )
        if not await confirm(question, "Check"):
            return
        try:
            results = await api.check_all_members(token())
        except api.ApiError as problem:
            ui.notify(problem.message, type="negative")
            return
        _show_results(
            "Members checked",
            [
                (f"{r['title']}: {r['message']}", not r["message"].startswith("Failed"))
                for r in results
            ],
        )
        await after()

    ui.button("Create repos for all Projects", on_click=create).props(
        "outline color=dark"
    ).mark("create-repos")
    ui.button("Check all members", on_click=check_all).props("outline color=dark").mark(
        "check-all-members"
    )
