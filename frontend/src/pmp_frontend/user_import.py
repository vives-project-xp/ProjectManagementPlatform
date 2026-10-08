"""Generated Temporary passwords, shown once, and importing Users from a CSV
file (#56)."""

import csv
import io
from collections.abc import Awaitable, Callable
from typing import Any

from nicegui import events, ui

from pmp_frontend import api
from pmp_frontend.shell import ErrorMessage, token

ROLES = {"teacher": "Teacher", "student": "Student"}
YEARS = ["1", "2", "3", "International"]


def show_temporary_password(name: str, password: str) -> None:
    """A dialog with the generated password: the only time anyone sees it."""
    with ui.dialog() as dialog, ui.card().classes("w-full max-w-md"):
        ui.label(f"Temporary password for {name}").classes("text-h6")
        ui.label(password).classes("text-h5 font-mono").mark("shown-password")
        ui.label(
            "Give it to them now: it is shown only once. They choose their own "
            "password at their first login."
        ).classes("text-caption")
        with ui.row():
            ui.button("Copy", on_click=lambda: ui.clipboard.write(password)).props(
                "outline color=dark"
            )
            ui.button("Done", on_click=dialog.close).mark("password-done")
    dialog.open()


def passwords_csv(created: list[dict[str, Any]]) -> bytes:
    """The created Users with their Temporary passwords, to hand out."""
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["Firstname", "Lastname", "email", "temporary password"])
    for user in created:
        writer.writerow(
            [
                user["first_name"],
                user["last_name"],
                user["email"],
                user["temporary_password"],
            ]
        )
    # With a BOM, so Excel shows accents correctly.
    return out.getvalue().encode("utf-8-sig")


def _show_result(result: dict[str, Any]) -> None:
    created, skipped = result["created"], result["skipped"]
    with ui.dialog() as dialog, ui.card().classes("w-full max-w-lg"):
        ui.label("Import done").classes("text-h6")
        ui.label(
            f"{len(created)} User{'s' if len(created) != 1 else ''} created, "
            f"{len(skipped)} line{'s' if len(skipped) != 1 else ''} skipped."
        ).mark("import-summary")
        for line in skipped:
            ui.label(f"Line {line['line']}: {line['reason']}").classes("text-negative")
        if created:
            ui.label(
                "Download the Temporary passwords now: they are shown only this once."
            ).classes("text-caption")
            ui.button(
                "Download the passwords",
                on_click=lambda: ui.download.content(
                    passwords_csv(created), "temporary-passwords.csv", "text/csv"
                ),
            ).mark("download-passwords")
        ui.button("Done", on_click=dialog.close).props("flat color=dark").mark(
            "import-done"
        )
    dialog.open()


def import_button(programmes: list[str], after: Callable[[], Awaitable[None]]) -> None:
    """The "Import CSV" button and its dialog; `after` reloads the Users table."""

    async def upload(event: events.UploadEventArguments) -> None:
        if role.value == "student" and (not programme.value or not year.value):
            error.show("Choose the Programme and Year of these Students first.")
            uploader.reset()
            return
        try:
            result = await api.import_users(
                token(),
                event.file.name,
                await event.file.read(),
                role=role.value,
                programme=programme.value if role.value == "student" else None,
                year=year.value if role.value == "student" else None,
            )
        except api.ApiError as problem:
            error.show(problem.message)
            uploader.reset()
            return
        dialog.close()
        _show_result(result)
        await after()

    with ui.dialog() as dialog, ui.card().classes("w-full max-w-md"):
        ui.label("Import Users from a CSV file").classes("text-h6")
        ui.label(
            "One User per line: Firstname,Lastname,email (a header line is fine). "
            "Everyone gets their own generated Temporary password."
        ).classes("text-caption")
        role = ui.toggle(ROLES, value="student").mark("import-role")
        with ui.column().classes("w-full") as student_fields:
            programme = (
                ui.select(
                    programmes,
                    label="Programme",
                    value=programmes[0] if len(programmes) == 1 else None,
                )
                .classes("w-full")
                .mark("import-programme")
            )
            year = ui.select(YEARS, label="Year").classes("w-full").mark("import-year")
        student_fields.bind_visibility_from(role, "value", value="student")
        error = ErrorMessage()
        uploader = (
            ui.upload(label="Choose the CSV file", auto_upload=True, on_upload=upload)
            .props('accept=".csv,text/csv" flat bordered')
            .classes("w-full")
            .mark("import-file")
        )
        ui.button("Cancel", on_click=dialog.close).props("flat color=dark")

    ui.button("Import CSV", on_click=dialog.open).props("outline color=dark").mark(
        "import-users"
    )
