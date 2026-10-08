"""The Projects screen and a Project's details page (Teachers and the Superuser)."""

from collections.abc import Callable
from typing import Any

from nicegui import ui
from starlette.responses import Response

from pmp_frontend import api
from pmp_frontend.photos import THUMBNAIL_CELL, photo_card, photo_url
from pmp_frontend.shell import (
    ErrorMessage,
    confirm,
    guard,
    no_access,
    page_frame,
    role_page,
    token,
)

STAFF = {"superuser", "teacher"}

COLUMNS = [
    {"name": "photo", "label": "", "field": "photo", "align": "left"},
    {
        "name": "title",
        "label": "Title",
        "field": "title",
        "sortable": True,
        "align": "left",
    },
    {"name": "owner", "label": "Product Owner", "field": "owner", "align": "left"},
    {"name": "members", "label": "Members", "field": "members", "align": "left"},
    {"name": "status", "label": "Status", "field": "status", "align": "left"},
]

# Understaffed Projects get a VIVES-red warning icon; the text itself stays black.
MEMBERS_CELL = """
<q-td :props="props">
  <q-icon v-if="props.row.understaffed" name="warning" color="primary"
          class="q-mr-xs" title="Fewer Members than the minimum Team size" />
  {{ props.value }}
</q-td>
"""


def _team_size_label(project: dict[str, Any]) -> str:
    """Members against the Team size, e.g. "3 / 4–6"."""
    return (
        f"{project['member_count']} / "
        f"{project['team_size_min']}–{project['team_size_max']}"
    )


def _row(project: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": project["id"],
        "photo": photo_url(project["id"], project["photo_version"]) or "",
        "title": project["title"],
        "owner": project["product_owner"]["name"],
        "members": _team_size_label(project),
        "understaffed": project["member_count"] < project["team_size_min"],
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
            found = await api.list_projects(token(), status=status_filter.value)
            table.rows = [_row(project) for project in found]

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
        # Active Projects are the current work; Archived ones the history overview.
        status_filter = ui.toggle(
            {"active": "Active", "archived": "Archived"},
            value="active",
            on_change=refresh,
        ).mark("status-filter")
        table = ui.table(columns=COLUMNS, rows=[], row_key="id").classes("w-full")
        table.mark("projects")
        table.add_slot("body-cell-photo", THUMBNAIL_CELL)
        table.add_slot("body-cell-members", MEMBERS_CELL)
        table.on(
            "rowClick", lambda event: ui.navigate.to(f"/projects/{event.args[1]['id']}")
        )
        await refresh()

    @ui.page("/projects/{project_id}")
    async def project_details(project_id: int) -> Response | None:
        user = await guard()
        if isinstance(user, Response):
            return user
        with page_frame("Project", user):
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

            async def change_status() -> None:
                title = project["title"]
                if archived:
                    question = f"Restore {title}? It becomes active without Members."
                    action, change = "Restore", api.restore_project
                else:
                    question = (
                        f"Archive {title}? Its Members are saved as Makers and "
                        "freed for other Projects, and it becomes read-only."
                    )
                    action, change = "Archive", api.archive_project
                if not await confirm(question, action):
                    return
                try:
                    await change(token(), project_id)
                except api.ApiError as error:
                    status_error.show(error.message)
                    return
                ui.navigate.to(f"/projects/{project_id}")

            async def delete() -> None:
                title = project["title"]
                if not await confirm(f"Delete {title}?", "Delete"):
                    return
                try:
                    await api.delete_project(token(), project_id)
                except api.ApiError as error:
                    status_error.show(error.message)
                    return
                ui.notify(f"Project {title} was deleted.")
                ui.navigate.to("/projects")

            archived = project["status"] == "archived"
            ui.link("← Projects", "/projects").classes("text-dark")
            heading = ui.label(project["title"]).classes("text-h4")
            with ui.row().classes("items-center gap-4"):
                ui.label(f"Status: {project['status'].capitalize()}")
                ui.button(
                    "Restore" if archived else "Archive", on_click=change_status
                ).props("outline color=dark").mark("change-status")
                # Only Active Projects without Makers can be deleted (the backend
                # also refuses one with Members, with a message).
                if not archived and not project["makers"]:
                    ui.button("Delete", on_click=delete).props(
                        "outline color=negative"
                    ).mark("delete-project")
            status_error = ErrorMessage()
            photo_card(project, editable=not archived)
            if archived:
                # Archived Projects are read-only: shown, never edited.
                with ui.card().classes("w-full max-w-lg"):
                    _read_only_details(project)
            else:
                with ui.card().classes("w-full max-w-lg"):
                    read_fields = _project_form(teachers, project)
                    error_message = ErrorMessage()
                    ui.button("Save", on_click=save).mark("save-project")
                with ui.card().classes("w-full max-w-lg"):
                    await _members_section(project)
            if project["makers"]:
                with ui.card().classes("w-full max-w-lg"):
                    ui.label("Made by").classes("text-h6")
                    for maker in project["makers"]:
                        ui.label(_maker_label(maker))
        return None


async def _members_section(project: dict[str, Any]) -> None:
    """The Members list with add (and move) and remove, each confirmed."""
    state = {"project": project, "students": await api.students(token())}

    async def reload(details: dict[str, Any]) -> None:
        state["project"] = details
        state["students"] = await api.students(token())
        members.refresh()
        update_choices()

    def update_choices() -> None:
        # Active Students who are not yet in this Project (others can be moved).
        choice.set_options(
            {
                student["id"]: _student_option(student)
                for student in state["students"]
                if student["is_active"]
                and (student["project"] or {}).get("id") != state["project"]["id"]
            },
            value=None,
        )

    async def add() -> None:
        student_id = choice.value
        if student_id is None:
            add_error.show("Choose a Student first.")
            return
        try:
            details = await api.add_member(token(), project["id"], student_id)
        except api.ApiError as error:
            if error.code != api.MOVE_CONFIRMATION_NEEDED:
                add_error.show(error.message)
                return
            if not await confirm(error.message, "Move"):
                return
            try:
                details = await api.add_member(
                    token(), project["id"], student_id, confirm_move=True
                )
            except api.ApiError as move_error:
                add_error.show(move_error.message)
                return
        add_error.hide()
        await reload(details)
        ui.notify("The Member was added.")

    async def remove(member: dict[str, Any]) -> None:
        title = state["project"]["title"]
        if not await confirm(f"Remove {member['name']} from {title}?", "Remove"):
            return
        try:
            details = await api.remove_member(token(), project["id"], member["id"])
        except api.ApiError as error:
            add_error.show(error.message)
            return
        await reload(details)
        ui.notify(f"{member['name']} was removed.")

    @ui.refreshable
    def members() -> None:
        current = state["project"]
        ui.label(f"Members ({_team_size_label(current)})").classes("text-h6")
        if not current["members"]:
            ui.label("No Members yet.")
        for member in current["members"]:
            with ui.row().classes("w-full items-center"):
                label = ui.label(_member_label(member))
                if not member["is_active"]:
                    # Greyed out (60% black, house style) but still counted.
                    label.style("color: #666666")
                ui.space()
                ui.button("Remove", on_click=lambda m=member: remove(m)).props(
                    "flat color=dark"
                ).mark("remove-member")

    members()
    choice = ui.select({}, label="Add a Student", with_input=True).classes("w-full")
    choice.mark("student-choice")
    update_choices()
    add_error = ErrorMessage()
    ui.button("Add Member", on_click=add).mark("add-member")


def _read_only_details(project: dict[str, Any]) -> None:
    ui.label(project["description"] or "No description.")
    ui.label(f"Product Owner: {project['product_owner']['name']}")
    ui.label(f"Team size: {project['team_size_min']}–{project['team_size_max']}")


def _maker_label(person: dict[str, Any]) -> str:
    """Name, Programme and Year: how a Maker is listed under "Made by"."""
    return f"{person['name']} — {person['programme']}, year {person['year']}"


def _member_label(member: dict[str, Any]) -> str:
    suffix = " (deactivated)" if not member["is_active"] else ""
    return f"{_maker_label(member)}{suffix}"


def _student_option(student: dict[str, Any]) -> str:
    project = student["project"]
    where = project["title"] if project else "no Project yet"
    return f"{student['name']} ({where})"
