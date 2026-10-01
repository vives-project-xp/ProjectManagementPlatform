"""The Programmes screen: the list a Student's Programme is picked from (Superuser)."""

from typing import Any

from nicegui import ui

from pmp_frontend import api
from pmp_frontend.shell import ErrorMessage, confirm, role_page, token


def register() -> None:
    @role_page("/programmes", "Programmes", {"superuser"})
    async def programmes_page(user: api.CurrentUser) -> None:
        async def reload() -> None:
            listed = await api.list_programmes(token())
            rows.clear()
            with rows:
                for programme in listed:
                    _programme_row(programme)

        def _programme_row(programme: dict[str, Any]) -> None:
            key = programme["id"]
            with ui.row().classes("w-full items-center gap-2"):
                ui.label(programme["name"]).classes("grow")
                ui.button(
                    "Rename", icon="edit", on_click=lambda: open_rename(programme)
                ).props("flat color=dark").mark(f"rename-programme-{key}")
                ui.button(
                    "Remove", icon="delete", on_click=lambda: remove(programme)
                ).props("flat color=dark").mark(f"remove-programme-{key}")

        async def add() -> None:
            try:
                added = await api.add_programme(token(), new_name.value)
            except api.ApiError as error:
                error_message.show(error.message)
                return
            error_message.hide()
            new_name.value = ""
            ui.notify(f"Programme {added['name']} was added.")
            await reload()

        def open_rename(programme: dict[str, Any]) -> None:
            renaming["programme"] = programme
            rename_input.value = programme["name"]
            rename_error.hide()
            rename_dialog.open()

        async def rename() -> None:
            programme = renaming["programme"]
            try:
                renamed = await api.rename_programme(
                    token(), programme["id"], rename_input.value
                )
            except api.ApiError as error:
                rename_error.show(error.message)
                return
            rename_dialog.close()
            ui.notify(f"{programme['name']} was renamed to {renamed['name']}.")
            await reload()

        async def remove(programme: dict[str, Any]) -> None:
            if not await confirm(
                f"Remove the Programme {programme['name']}?", "Remove"
            ):
                return
            try:
                await api.remove_programme(token(), programme["id"])
            except api.ApiError as error:
                error_message.show(error.message)
                return
            error_message.hide()
            ui.notify(f"Programme {programme['name']} was removed.")
            await reload()

        renaming: dict[str, Any] = {}
        with ui.dialog() as rename_dialog, ui.card().classes("w-full max-w-md"):
            ui.label("Rename Programme").classes("text-h6")
            ui.label("Every User with this Programme gets the new name.")
            rename_input = (
                ui.input("Name").classes("w-full").mark("programme-name")
            ).on("keydown.enter", rename)
            rename_error = ErrorMessage()
            with ui.row():
                ui.button("Save", on_click=rename).mark("save-programme")
                ui.button("Cancel", on_click=rename_dialog.close).props(
                    "flat color=dark"
                )

        ui.label("Programmes").classes("text-h4")
        ui.label("A Student's Programme is picked from this list.")
        with ui.card().classes("w-full max-w-xl"):
            with ui.row().classes("w-full items-center gap-2"):
                new_name = (
                    ui.input("New Programme")
                    .classes("grow")
                    .mark("new-programme")
                    .on("keydown.enter", add)
                )
                ui.button("Add", icon="add", on_click=add).mark("add-programme")
            error_message = ErrorMessage()
            rows = ui.column().classes("w-full gap-1").mark("programmes")
        await reload()
