"""Deadlines (spec #68): the Planning card on a Project's page and on My project,
the Planning screen, and the Today banner."""

from collections.abc import Awaitable, Callable
from itertools import groupby
from typing import Any

from nicegui import ui

from pmp_frontend import api
from pmp_frontend.shell import ErrorMessage, confirm, role_page, token
from pmp_frontend.times import local, moment_from

STAFF = {"superuser", "teacher"}


def _time(deadline: dict[str, Any]) -> str:
    return local(deadline["due_at"]).strftime("%H:%M")


def _day(deadline: dict[str, Any]) -> str:
    return local(deadline["due_at"]).strftime("%A %d/%m/%Y")


def _for_whom(deadline: dict[str, Any]) -> str:
    return deadline["project_title"] or "All Projects"


def today_banner(deadlines: list[dict[str, Any]], *, show_project: bool) -> None:
    """What is due today, so nobody misses it; nothing on a quiet day."""
    today = [d for d in deadlines if d["when"] == "today"]
    if not today:
        return
    with ui.card().classes("w-full bg-[#efeee9]").mark("today-banner"):
        ui.label("Today").classes("text-h6")
        for deadline in today:
            project = f" ({_for_whom(deadline)})" if show_project else ""
            ui.label(f"{_time(deadline)} · {deadline['title']}{project}")


async def _deadline_dialog(deadline: dict[str, Any] | None = None) -> dict | None:
    """The fields of a new or changed deadline, or None when cancelled."""
    due = local(deadline["due_at"]) if deadline else None
    with ui.dialog() as dialog, ui.card().classes("w-full max-w-md"):
        ui.label("Change deadline" if deadline else "New deadline").classes("text-h6")
        title = ui.input("Title", value=deadline["title"] if deadline else "")
        title.classes("w-full").mark("deadline-title")
        with ui.row().classes("w-full"):
            date = ui.input("Date", value=due.strftime("%Y-%m-%d") if due else "")
            date.props("type=date stack-label").mark("deadline-date")
            time = ui.input(
                "Time (Belgian time)", value=due.strftime("%H:%M") if due else "23:59"
            )
            time.props("type=time stack-label").mark("deadline-time")
        description = ui.textarea(
            "Description (optional)",
            value=(deadline or {}).get("description") or "",
        )
        description.classes("w-full").mark("deadline-description")
        error = ErrorMessage()

        def save() -> None:
            due_at = moment_from(date.value or "", time.value or "")
            if not (title.value or "").strip():
                error.show("Give the deadline a title.")
            elif due_at is None:
                error.show("Choose a date and a time.")
            else:
                dialog.submit(
                    {
                        "title": title.value,
                        "due_at": due_at,
                        "description": description.value or None,
                    }
                )

        with ui.row():
            ui.button("Save", on_click=save).mark("save-deadline")
            ui.button("Cancel", on_click=lambda: dialog.submit(None)).props(
                "flat color=dark"
            )
    result = await dialog
    dialog.delete()
    return result


def _deadline_row(
    deadline: dict[str, Any],
    *,
    show_project: bool,
    change: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    delete: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
) -> None:
    with ui.row().classes("w-full items-center no-wrap gap-2") as line_row:
        if deadline["when"] == "earlier":
            # Past deadlines are greyed out (brand grey: 60% black).
            line_row.classes("text-grey-7")
        with ui.column().classes("gap-0 grow"):
            when = local(deadline["due_at"]).strftime("%d/%m/%Y %H:%M")
            line = ui.label(f"{when} · {deadline['title']}")
            if deadline["when"] == "today":
                line.classes("font-medium")
            if show_project or deadline["project_id"] is None:
                ui.label(_for_whom(deadline)).classes("text-caption")
            if deadline["description"]:
                ui.label(deadline["description"]).classes("text-caption")
        if change:
            ui.button(icon="edit", on_click=lambda: change(deadline)).props(
                "flat dense color=dark"
            ).mark("edit-deadline")
        if delete:
            ui.button(icon="delete", on_click=lambda: delete(deadline)).props(
                "flat dense color=dark"
            ).mark("delete-deadline")


async def _change(deadline: dict[str, Any], after) -> None:
    fields = await _deadline_dialog(deadline)
    if fields is None:
        return
    try:
        await api.update_deadline(token(), deadline["id"], fields)
    except api.ApiError as problem:
        ui.notify(problem.message, type="negative")
        return
    ui.notify("The deadline was changed.")
    after()


async def _delete(deadline: dict[str, Any], after) -> None:
    if not await confirm(f"Delete the deadline {deadline['title']}?", "Delete"):
        return
    try:
        await api.delete_deadline(token(), deadline["id"])
    except api.ApiError as problem:
        ui.notify(problem.message, type="negative")
        return
    ui.notify("The deadline was deleted.")
    after()


def _deadline_lists(deadlines: list[dict[str, Any]], row) -> None:
    """Upcoming (today first) and, folded away, the earlier ones."""
    coming = [d for d in deadlines if d["when"] != "earlier"]
    earlier = [d for d in deadlines if d["when"] == "earlier"]
    if not coming:
        ui.label("Nothing coming up.").classes("text-caption")
    for deadline in coming:
        row(deadline)
    if earlier:
        with ui.expansion(f"Earlier ({len(earlier)})").classes("w-full text-grey-7"):
            for deadline in reversed(earlier):
                row(deadline)


async def planning_card(project: dict[str, Any], *, editable: bool) -> None:
    """A Project's deadlines (its own and those for every Project); Teachers add,
    change and delete its own ones while it is Active."""

    @ui.refreshable
    async def content() -> None:
        deadlines = await api.project_deadlines(token(), project["id"])
        today_banner(deadlines, show_project=False)

        def row(deadline: dict[str, Any]) -> None:
            # Deadlines for every Project are changed on the Planning screen.
            own = editable and deadline["project_id"] == project["id"]
            _deadline_row(
                deadline,
                show_project=False,
                change=(lambda d: _change(d, content.refresh)) if own else None,
                delete=(lambda d: _delete(d, content.refresh)) if own else None,
            )

        _deadline_lists(deadlines, row)

    async def add() -> None:
        fields = await _deadline_dialog()
        if fields is None:
            return
        try:
            await api.add_deadline(token(), project["id"], fields)
        except api.ApiError as problem:
            ui.notify(problem.message, type="negative")
            return
        ui.notify(f"The deadline {fields['title']} was added.")
        content.refresh()

    with ui.card().classes("w-full max-w-lg").mark("planning-card"):
        ui.label("Planning").classes("text-h6")
        await content()
        if editable:
            ui.button("Add deadline", on_click=add).props("outline color=dark").mark(
                "add-deadline"
            )


async def my_planning_card() -> None:
    """On My project: the Student's Project's deadlines, read-only."""
    deadlines = await api.my_planning(token())
    with ui.card().classes("w-full").mark("my-planning"):
        ui.label("Planning").classes("text-h6")
        today_banner(deadlines, show_project=False)
        _deadline_lists(
            deadlines, lambda deadline: _deadline_row(deadline, show_project=False)
        )


def register() -> None:
    @role_page("/planning", "Planning", STAFF)
    async def planning_page(user: api.CurrentUser) -> None:
        @ui.refreshable
        async def content() -> None:
            deadlines = await api.planning(token(), mine=only_mine.value)
            today_banner(deadlines, show_project=True)

            def row(deadline: dict[str, Any]) -> None:
                # Here the deadlines for every Project are changed.
                for_all = deadline["project_id"] is None
                _deadline_row(
                    deadline,
                    show_project=True,
                    change=(lambda d: _change(d, content.refresh)) if for_all else None,
                    delete=(lambda d: _delete(d, content.refresh)) if for_all else None,
                )

            if not deadlines:
                ui.label("Nothing coming up.")
            for day, on_day in groupby(deadlines, key=_day):
                ui.label(day).classes("text-subtitle1 font-medium q-mt-md")
                for deadline in on_day:
                    row(deadline)

        async def add_for_all() -> None:
            fields = await _deadline_dialog()
            if fields is None:
                return
            try:
                await api.add_deadline(token(), None, fields)
            except api.ApiError as problem:
                ui.notify(problem.message, type="negative")
                return
            ui.notify(f"The deadline {fields['title']} was added for all Projects.")
            content.refresh()

        with ui.row().classes("w-full items-center"):
            ui.label("Planning").classes("text-h4")
            ui.space()
            ui.button("New deadline for all Projects", on_click=add_for_all).props(
                "outline color=dark"
            ).mark("add-deadline-for-all")
        only_mine = ui.checkbox(
            "Only my Projects", on_change=lambda: content.refresh()
        ).mark("only-mine")
        with ui.column().classes("w-full max-w-2xl").mark("planning"):
            await content()
