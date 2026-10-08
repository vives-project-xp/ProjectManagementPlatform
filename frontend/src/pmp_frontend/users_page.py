"""The Users screen and a User's details page (Superuser only)."""

from typing import Any

from nicegui import ui
from starlette.responses import Response

from pmp_frontend import api
from pmp_frontend.github_username import github_username_card
from pmp_frontend.shell import (
    ErrorMessage,
    confirm,
    guard,
    no_access,
    page_frame,
    role_page,
    token,
)
from pmp_frontend.user_import import (
    ROLES,
    YEARS,
    import_button,
    show_temporary_password,
)

ROLE_FILTER = {"": "All", "superuser": "Superuser"} | ROLES
# Status filter label -> the backend's `active` value.
STATUS_FILTER: dict[str, bool | None] = {"": None, "Active": True, "Deactivated": False}
# Fixed list (ADR 0004); Programmes come from the backend because they will
# become manageable later.

COLUMNS = [
    {
        "name": "name",
        "label": "Name",
        "field": "name",
        "sortable": True,
        "align": "left",
    },
    {"name": "email", "label": "Email", "field": "email", "align": "left"},
    {"name": "github", "label": "GitHub", "field": "github", "align": "left"},
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
        "github": user["github_username"] or "",
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
            listed = await api.list_users(
                token(),
                role=role_filter.value or None,
                active=STATUS_FILTER[status_filter.value],
            )
            table.rows = [_row(found) for found in listed]

        async def create() -> None:
            new_user: dict[str, Any] = {
                "role": role.value,
                "first_name": first_name.value,
                "last_name": last_name.value,
                "email": email.value,
            }
            if role.value == "student":
                new_user |= {"programme": programme.value, "year": year.value}
            try:
                created = await api.create_user(token(), new_user)
            except api.ApiError as error:
                error_message.show(error.message)
                return
            dialog.close()
            name = f"{created['first_name']} {created['last_name']}"
            ui.notify(f"{name} was created.")
            show_temporary_password(name, created["temporary_password"])
            await refresh()

        def open_dialog() -> None:
            for field in (first_name, last_name, email):
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
            ui.label(
                "A Temporary password is generated and shown after creating."
            ).classes("text-caption")
            error_message = ErrorMessage()
            with ui.row():
                ui.button("Create", on_click=create).mark("create-user")
                ui.button("Cancel", on_click=dialog.close).props("flat color=dark")

        with ui.row().classes("w-full items-center"):
            ui.label("Users").classes("text-h4")
            ui.space()
            import_button(programmes, refresh)
            ui.button("New user", on_click=open_dialog).mark("new-user")
        with ui.row().classes("items-center gap-4"):
            role_filter = ui.select(
                ROLE_FILTER, value="", label="Role", on_change=refresh
            ).classes("w-40")
            role_filter.mark("role-filter")
            status_filter = ui.select(
                {key: key or "All" for key in STATUS_FILTER},
                value="",
                label="Status",
                on_change=refresh,
            ).classes("w-40")
            status_filter.mark("status-filter")
        table = ui.table(columns=COLUMNS, rows=[], row_key="id").classes("w-full")
        table.mark("users")
        table.on(
            "rowClick", lambda event: ui.navigate.to(f"/users/{event.args[1]['id']}")
        )
        await refresh()

    @ui.page("/users/{user_id}")
    async def user_details(user_id: int) -> Response | None:
        user = await guard()
        if isinstance(user, Response):
            return user
        with page_frame("User", user):
            if user.role != "superuser":
                no_access()
                return None
            try:
                shown = await api.get_user(token(), user_id)
            except api.ApiError as error:
                ui.label(error.message)
                return None
            programmes = await api.programmes(token())
            is_student = shown["role"] == "student"

            async def save() -> None:
                fields = {
                    "first_name": first_name.value,
                    "last_name": last_name.value,
                    "email": email.value,
                    "programme": programme.value if is_student else None,
                    "year": year.value if is_student else None,
                }
                try:
                    saved = await api.update_user(token(), user_id, fields)
                except api.ApiError as error:
                    error_message.show(error.message)
                    return
                error_message.hide()
                heading.text = f"{saved['first_name']} {saved['last_name']}"
                ui.notify("The changes were saved.")

            async def toggle_active() -> None:
                try:
                    change = (
                        api.deactivate_user
                        if shown["is_active"]
                        else api.reactivate_user
                    )
                    changed = await change(token(), user_id)
                except api.ApiError as error:
                    status_error.show(error.message)
                    return
                status_error.hide()
                shown["is_active"] = changed["is_active"]
                show_status()
                ui.notify(
                    "The User was reactivated."
                    if changed["is_active"]
                    else "The User was deactivated."
                )

            async def reset() -> None:
                name = f"{shown['first_name']} {shown['last_name']}"
                question = (
                    f"Reset the password of {name}? They get a new Temporary "
                    "password and must choose their own at the next login."
                )
                if not await confirm(question, "Reset"):
                    return
                try:
                    password = await api.reset_password(token(), user_id)
                except api.ApiError as error:
                    reset_error.show(error.message)
                    return
                reset_error.hide()
                show_temporary_password(name, password)

            async def delete() -> None:
                name = f"{shown['first_name']} {shown['last_name']}"
                if not await confirm(f"Delete the User {name}?", "Delete"):
                    return
                try:
                    await api.delete_user(token(), user_id)
                except api.ApiError as error:
                    delete_error.show(error.message)
                    return
                ui.notify(f"{name} was deleted.")
                ui.navigate.to("/users")

            def show_status() -> None:
                active = shown["is_active"]
                status_label.text = f"Status: {'Active' if active else 'Deactivated'}"
                status_button.text = "Deactivate" if active else "Reactivate"

            ui.link("← Users", "/users").classes("text-dark")
            heading = ui.label(f"{shown['first_name']} {shown['last_name']}").classes(
                "text-h4"
            )
            # The Role is fixed at creation, so it is shown, never edited.
            ui.label(f"Role: {shown['role'].capitalize()}")

            with ui.card().classes("w-full max-w-lg"):
                ui.label("Details").classes("text-h6")
                first_name = ui.input("First name", value=shown["first_name"])
                first_name.classes("w-full").mark("first-name")
                last_name = ui.input("Last name", value=shown["last_name"])
                last_name.classes("w-full").mark("last-name")
                email = ui.input("Email", value=shown["email"])
                email.classes("w-full").mark("edit-email")
                programme = ui.select(
                    programmes, label="Programme", value=shown["programme"]
                ).classes("w-full")
                year = ui.select(YEARS, label="Year", value=shown["year"]).classes(
                    "w-full"
                )
                programme.set_visibility(is_student)
                year.set_visibility(is_student)
                error_message = ErrorMessage()
                ui.button("Save", on_click=save).mark("save-user")

            with ui.card().classes("w-full max-w-lg"):
                status_label = ui.label()
                status_error = ErrorMessage()
                status_button = ui.button(on_click=toggle_active).mark("toggle-active")
                show_status()

            with ui.card().classes("w-full max-w-lg"):
                ui.label("Reset password").classes("text-h6")
                ui.label("Generates a new Temporary password, shown once.").classes(
                    "text-caption"
                )
                reset_error = ErrorMessage()
                ui.button("Reset password", on_click=reset).mark("reset-password")

            github_username_card(
                shown["github_username"],
                lambda username: api.set_github_username(token(), user_id, username),
            )

            # The Superuser can never be deleted, so their page has no Delete.
            if shown["role"] != "superuser":
                with ui.card().classes("w-full max-w-lg"):
                    ui.label("Delete User").classes("text-h6")
                    ui.label(
                        "Only possible when the User is not linked to any Project; "
                        "otherwise, deactivate them."
                    )
                    delete_error = ErrorMessage()
                    ui.button("Delete", on_click=delete).props("color=negative").mark(
                        "delete-user"
                    )
        return None
