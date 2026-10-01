"""The Users screen: the Superuser sees every User and creates Teachers and Students."""

from typing import Any

from nicegui import ui

from pmp_frontend import api
from pmp_frontend.shell import ErrorMessage, role_page, token

ROLES = {"teacher": "Teacher", "student": "Student"}
# Fixed list (ADR 0004); Programmes come from the backend because they will
# become manageable later.
YEARS = ["1", "2", "3", "International"]

COLUMNS = [
    {
        "name": "name",
        "label": "Name",
        "field": "name",
        "sortable": True,
        "align": "left",
    },
    {"name": "email", "label": "Email", "field": "email", "align": "left"},
    {
        "name": "role",
        "label": "Role",
        "field": "role",
        "sortable": True,
        "align": "left",
    },
    {"name": "programme", "label": "Programme", "field": "programme", "align": "left"},
    {"name": "year", "label": "Year", "field": "year", "align": "left"},
    {"name": "status", "label": "Status", "field": "status", "align": "left"},
]


def _row(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": user["id"],
        "name": f"{user['first_name']} {user['last_name']}",
        "email": user["email"],
        "role": user["role"].capitalize(),
        "programme": user["programme"] or "",
        "year": user["year"] or "",
        "status": "Active" if user["is_active"] else "Deactivated",
    }


def register() -> None:
    @role_page("/users", "Users", {"superuser"})
    async def users_page(user: api.CurrentUser) -> None:
        programmes = await api.programmes(token())

        async def refresh() -> None:
            table.rows = [_row(listed) for listed in await api.list_users(token())]

        async def create() -> None:
            new_user: dict[str, Any] = {
                "role": role.value,
                "first_name": first_name.value,
                "last_name": last_name.value,
                "email": email.value,
                "temporary_password": temporary_password.value,
            }
            if role.value == "student":
                new_user |= {"programme": programme.value, "year": year.value}
            try:
                created = await api.create_user(token(), new_user)
            except api.ApiError as error:
                error_message.show(error.message)
                return
            dialog.close()
            ui.notify(f"{created['first_name']} {created['last_name']} was created.")
            await refresh()

        def open_dialog() -> None:
            for field in (first_name, last_name, email, temporary_password):
                field.value = ""
            programme.value = programmes[0] if len(programmes) == 1 else None
            year.value = None
            error_message.hide()
            dialog.open()

        with ui.dialog() as dialog, ui.card().classes("w-full max-w-md"):
            ui.label("New user").classes("text-h6")
            role = ui.toggle(ROLES, value="teacher").mark("role")
            first_name = ui.input("First name").classes("w-full").mark("first-name")
            last_name = ui.input("Last name").classes("w-full").mark("last-name")
            email = ui.input("Email").classes("w-full").mark("new-email")
            with ui.column().classes("w-full") as student_fields:
                programme = (
                    ui.select(programmes, label="Programme")
                    .classes("w-full")
                    .mark("programme")
                )
                year = ui.select(YEARS, label="Year").classes("w-full").mark("year")
            student_fields.bind_visibility_from(role, "value", value="student")
            temporary_password = (
                ui.input("Temporary password (at least 8 characters)")
                .classes("w-full")
                .mark("temporary-password")
            )
            error_message = ErrorMessage()
            with ui.row():
                ui.button("Create", on_click=create).mark("create-user")
                ui.button("Cancel", on_click=dialog.close).props("flat color=dark")

        with ui.row().classes("w-full items-center"):
            ui.label("Users").classes("text-h4")
            ui.space()
            ui.button("New user", on_click=open_dialog).mark("new-user")
        table = ui.table(columns=COLUMNS, rows=[], row_key="id").classes("w-full")
        table.mark("users")
        await refresh()
