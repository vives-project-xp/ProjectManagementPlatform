"""Clients on a Project (spec #132, #134): staff add and remove them and give
one the Client Product Owner label; everyone sees them by name and
Organisation."""

from typing import Any

from nicegui import ui

from pmp_frontend import api
from pmp_frontend.shell import ErrorMessage, confirm, token

LABEL = "Client Product Owner"


def client_label(person: dict[str, Any]) -> str:
    """ "Jan Peeters (Barco), Client Product Owner" """
    if person["is_client_product_owner"]:
        return f"{person['name']}, {LABEL}"
    return person["name"]


async def clients_section(project: dict[str, Any], *, editable: bool) -> None:
    """The Clients card on a Project's page; read-only for Archived Projects."""
    state = {"project": project}
    choices = await api.clients(token()) if editable else []

    async def run(call, done: str) -> None:
        try:
            state["project"] = await call
        except api.ApiError as problem:
            error.show(problem.message)
            return
        error.hide()
        people.refresh()
        update_choices()
        ui.notify(done)

    async def add() -> None:
        if choice.value is None:
            error.show("Choose a Client first.")
            return
        await run(
            api.add_client(token(), project["id"], choice.value),
            "The Client was added.",
        )

    async def remove(person: dict[str, Any]) -> None:
        title = state["project"]["title"]
        if not await confirm(f"Remove {person['name']} from {title}?", "Remove"):
            return
        await run(
            api.remove_client(token(), project["id"], person["id"]),
            f"{person['name']} was removed.",
        )

    async def label(person: dict[str, Any] | None) -> None:
        await run(
            api.set_client_product_owner(
                token(), project["id"], person["id"] if person else None
            ),
            "The label was saved.",
        )

    def update_choices() -> None:
        if not editable:
            return
        linked = {person["id"] for person in state["project"]["clients"]}
        choice.set_options(
            {c["id"]: c["name"] for c in choices if c["id"] not in linked}, value=None
        )

    @ui.refreshable
    def people() -> None:
        current = state["project"]["clients"]
        if not current:
            ui.label("No Clients follow this Project.")
        for person in current:
            with (
                ui.row()
                .classes("w-full items-center no-wrap")
                .mark(f"client-{person['id']}")
            ):
                ui.label(client_label(person)).classes("grow")
                if not editable:
                    continue
                if person["is_client_product_owner"]:
                    ui.button("Remove label", on_click=lambda: label(None)).props(
                        "flat dense color=dark"
                    ).mark("remove-label")
                else:
                    ui.button(
                        "Make Client Product Owner",
                        on_click=lambda p=person: label(p),
                    ).props("flat dense color=dark").mark("make-client-product-owner")
                ui.button("Remove", on_click=lambda p=person: remove(p)).props(
                    "flat dense color=dark"
                ).mark("remove-client")

    ui.label("Clients").classes("text-h6")
    ui.label(
        "People outside VIVES who follow this Project: they see it read-only "
        "and talk in its Chat. The label Client Product Owner is only a label."
    ).classes("text-caption")
    people()
    error = ErrorMessage()
    if editable:
        with ui.row().classes("w-full items-center no-wrap"):
            choice = ui.select({}, label="Add a Client", with_input=True).classes(
                "grow"
            )
            choice.mark("client-choice")
            ui.button("Add Client", icon="person_add", on_click=add).mark("add-client")
        update_choices()
