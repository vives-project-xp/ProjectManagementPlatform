"""Project repositories on GitHub (spec #49): the Repository card on a Project's
page and the "Create repos for all Projects" button."""

from typing import Any

from nicegui import ui

from pmp_frontend import api
from pmp_frontend.shell import ErrorMessage, confirm, token


def repository_card(project: dict[str, Any], *, editable: bool) -> None:
    """The repository's link once it exists; until then its name, editable."""

    async def save() -> None:
        try:
            saved = await api.set_repo_name(token(), project["id"], name.value or None)
        except api.ApiError as problem:
            error.show(problem.message)
            return
        error.hide()
        name.value = saved["repo_name"]
        ui.notify(f"The repository will be called {saved['repo_name']}.")

    with ui.card().classes("w-full max-w-lg").mark("repository-card"):
        ui.label("GitHub repository").classes("text-h6")
        if project["repo_url"]:
            ui.link(project["repo_url"], project["repo_url"], new_tab=True).mark(
                "repo-link"
            )
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
        error = ErrorMessage()
        ui.button("Save name", on_click=save).props("outline color=dark").mark(
            "save-repo-name"
        )


def _show_results(results: list[dict[str, Any]]) -> None:
    with ui.dialog() as dialog, ui.card().classes("w-full max-w-lg"):
        ui.label("Repositories").classes("text-h6")
        if not results:
            ui.label("Nothing to create.")
        for result in results:
            if result["created"]:
                ui.label(f"{result['title']}: Created")
            else:
                ui.label(f"{result['title']}: Failed. {result['message']}").classes(
                    "text-negative"
                )
        ui.button("Done", on_click=dialog.close).mark("repos-done")
    dialog.open()


async def create_repos_button(after) -> None:
    """The bulk button, or why it isn't there; `after` reloads the table."""
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
        _show_results(results)
        await after()

    ui.button("Create repos for all Projects", on_click=create).props(
        "outline color=dark"
    ).mark("create-repos")
