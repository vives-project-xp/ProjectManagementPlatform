"""My project: a Student's own Project, its Product Owner and fellow Members;
before they have one, their Top 3 (spec #37)."""

from typing import Any

from nicegui import ui

from pmp_frontend import api
from pmp_frontend.photos import show_photo
from pmp_frontend.shell import ErrorMessage, confirm, role_page, token
from pmp_frontend.top3_page import shown

RANKS = ["1st choice", "2nd choice", "3rd choice"]


def _top3_card(top3: dict[str, Any]) -> None:
    """Choose, or see the submitted Top 3, depending on the round."""
    round_ = top3["round"]

    async def submit() -> None:
        chosen = [choice.value for choice in choices]
        if None in chosen:
            error.show(f"Choose {len(choices)} different Projects.")
            return
        question = "Submit this top 3? You can't change it afterwards."
        if not await confirm(question, "Submit"):
            return
        try:
            await api.submit_top3(token(), chosen)
        except api.ApiError as problem:
            error.show(problem.message)
            return
        ui.navigate.to("/my-project")

    with ui.card().classes("w-full").mark("top3-card"):
        ui.label("Your top 3").classes("text-h6")
        if top3["top3"] is not None:
            for choice in top3["top3"]:
                title = choice["title"] or "A deleted Project"
                if not choice["available"]:
                    title += " (no longer available)"
                ui.label(f"{RANKS[choice['rank'] - 1]}: {title}")
            ui.label(f"Submitted on {shown(top3['submitted_at'])}.").classes(
                "text-caption"
            )
            return
        if round_["deadline"] is None:
            ui.label("Choosing opens later.")
            return
        if not round_["is_open"]:
            ui.label(
                f"The deadline ({shown(round_['deadline'])}) has passed. "
                "Contact a Teacher."
            )
            return
        if not top3["can_submit"]:
            ui.label("No Projects are open for choice yet. Choosing opens later.")
            return
        ui.label(f"Choose before {shown(round_['deadline'])} (Belgian time).")
        options = {project["id"]: project["title"] for project in top3["projects"]}
        choices = [
            ui.select(options, label=RANKS[place])
            .classes("w-full")
            .mark(f"choice-{place + 1}")
            for place in range(top3["places"])
        ]
        error = ErrorMessage()
        ui.button("Submit my top 3", on_click=submit).mark("submit-top3")

    ui.label("Projects to choose from").classes("text-h6")
    for project in top3["projects"]:
        with ui.card().classes("w-full"):
            show_photo(project["id"], project["photo_version"])
            ui.label(project["title"]).classes("text-h6")
            if project["description"]:
                ui.label(project["description"])
            ui.label(f"Product Owner: {project['product_owner']}")
            ui.label(
                f"Team size: {project['team_size_min']}–{project['team_size_max']}"
            )


def register() -> None:
    @role_page("/my-project", "My project", {"student"})
    async def my_project_page(user: api.CurrentUser) -> None:
        ui.label("My project").classes("text-h4")
        project = await api.my_project(token())
        if project is None:
            ui.label("You haven't been assigned to a project yet.")
            _top3_card(await api.my_top3(token()))
            return
        with ui.card().classes("w-full"):
            show_photo(project["id"], project["photo_version"])
            ui.label(project["title"]).classes("text-h5")
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
