"""Deadlines, Meetings and Weekly slots (spec #68): the Planning card on a
Project's page and on My project, the Planning screen, and the Today banner."""

from collections.abc import Awaitable, Callable
from itertools import groupby
from typing import Any

from nicegui import ui

from pmp_frontend import api
from pmp_frontend.shell import ErrorMessage, confirm, role_page, token
from pmp_frontend.times import local, moment_from

STAFF = {"superuser", "teacher"}
WEEKDAYS = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]

Item = dict[str, Any]


def _hours(item: Item) -> str:
    """ "14:00" for a deadline, "10:00–10:30" for a meeting."""
    start = local(item["starts_at"]).strftime("%H:%M")
    if item["ends_at"] is None:
        return start
    return f"{start}–{local(item['ends_at']).strftime('%H:%M')}"


def _day(item: Item) -> str:
    return local(item["starts_at"]).strftime("%A %d/%m/%Y")


def _for_whom(item: Item) -> str:
    return item["project_title"] or "All Projects"


def _place(place: str) -> None:
    """A room as text, an online meeting as a link."""
    if place.startswith(("http://", "https://")):
        ui.link(place, place, new_tab=True).classes("text-caption")
    else:
        ui.label(place).classes("text-caption")


def today_banner(items: list[Item], *, show_project: bool) -> None:
    """What happens today, so nobody misses it; nothing on a quiet day."""
    today = [item for item in items if item["when"] == "today"]
    if not today:
        return
    with ui.card().classes("w-full bg-[#efeee9]").mark("today-banner"):
        ui.label("Today").classes("text-h6")
        for item in today:
            project = f" ({_for_whom(item)})" if show_project else ""
            place = f" · {item['place']}" if item["place"] else ""
            ui.label(f"{_hours(item)} · {item['title']}{project}{place}")


# Dialogs: the fields of a new or changed item, or None when cancelled.


async def _deadline_dialog(deadline: Item | None = None) -> dict | None:
    due = local(deadline["starts_at"]) if deadline else None
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
            "Description (optional)", value=(deadline or {}).get("details") or ""
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

        _dialog_buttons(dialog, save, "save-deadline")
    result = await dialog
    dialog.delete()
    return result


async def _meeting_dialog(meeting: Item | None = None) -> dict | None:
    start = local(meeting["starts_at"]) if meeting else None
    end = local(meeting["ends_at"]) if meeting else None
    with ui.dialog() as dialog, ui.card().classes("w-full max-w-md"):
        ui.label("Change meeting" if meeting else "New meeting").classes("text-h6")
        date = ui.input("Date", value=start.strftime("%Y-%m-%d") if start else "")
        date.props("type=date stack-label").mark("meeting-date")
        with ui.row().classes("w-full"):
            starts = ui.input("From", value=start.strftime("%H:%M") if start else "")
            starts.props("type=time stack-label").mark("meeting-starts")
            ends = ui.input("Until", value=end.strftime("%H:%M") if end else "")
            ends.props("type=time stack-label").mark("meeting-ends")
        place = ui.input(
            "Place (a room or a meeting link)", value=(meeting or {}).get("place") or ""
        )
        place.classes("w-full").mark("meeting-place")
        note = ui.textarea(
            "Note (optional)", value=(meeting or {}).get("details") or ""
        )
        note.classes("w-full").mark("meeting-note")
        error = ErrorMessage()

        def save() -> None:
            starts_at = moment_from(date.value or "", starts.value or "")
            ends_at = moment_from(date.value or "", ends.value or "")
            if starts_at is None or ends_at is None:
                error.show("Choose a date and the times.")
            elif not (place.value or "").strip():
                error.show("Say where the meeting is.")
            else:
                dialog.submit(
                    {
                        "starts_at": starts_at,
                        "ends_at": ends_at,
                        "place": place.value,
                        "note": note.value or None,
                    }
                )

        _dialog_buttons(dialog, save, "save-meeting")
    result = await dialog
    dialog.delete()
    return result


async def _slot_dialog(slot: Item | None) -> dict | None:
    with ui.dialog() as dialog, ui.card().classes("w-full max-w-md"):
        ui.label("Weekly meeting").classes("text-h6")
        weekday = ui.select(
            dict(enumerate(WEEKDAYS)),
            value=slot["weekday"] if slot else 0,
            label="Every",
        ).mark("slot-weekday")
        with ui.row().classes("w-full"):
            starts = ui.input("From", value=slot["starts"][:5] if slot else "")
            starts.props("type=time stack-label").mark("slot-starts")
            ends = ui.input("Until", value=slot["ends"][:5] if slot else "")
            ends.props("type=time stack-label").mark("slot-ends")
        place = ui.input(
            "Place (a room or a meeting link)", value=slot["place"] if slot else ""
        )
        place.classes("w-full").mark("slot-place")
        error = ErrorMessage()

        def save() -> None:
            if not starts.value or not ends.value:
                error.show("Choose the times.")
            elif not (place.value or "").strip():
                error.show("Say where the meeting is.")
            else:
                dialog.submit(
                    {
                        "weekday": weekday.value,
                        "starts": starts.value,
                        "ends": ends.value,
                        "place": place.value,
                    }
                )

        _dialog_buttons(dialog, save, "save-slot")
    result = await dialog
    dialog.delete()
    return result


async def _skip_dialog(slot: Item) -> str | None:
    with ui.dialog() as dialog, ui.card().classes("w-full max-w-md"):
        ui.label(f"No weekly meeting on (a {slot['weekday_name']})").classes("text-h6")
        date = ui.input("Date").props("type=date stack-label").mark("skip-date")
        error = ErrorMessage()

        def save() -> None:
            if not date.value:
                error.show("Choose a date.")
            else:
                dialog.submit(date.value)

        _dialog_buttons(dialog, save, "save-skip")
    result = await dialog
    dialog.delete()
    return result


def _dialog_buttons(dialog: ui.dialog, save: Callable[[], None], marker: str) -> None:
    with ui.row():
        ui.button("Save", on_click=save).mark(marker)
        ui.button("Cancel", on_click=lambda: dialog.submit(None)).props(
            "flat color=dark"
        )


async def _call(call: Awaitable[Any], done: str, after: Callable[[], None]) -> None:
    """Run a change; show the refusal, or `done` and refresh."""
    try:
        await call
    except api.ApiError as problem:
        ui.notify(problem.message, type="negative")
        return
    ui.notify(done)
    after()


# Lists


def _item_row(
    item: Item,
    *,
    show_project: bool,
    change: Callable[[Item], Awaitable[None]] | None = None,
    delete: Callable[[Item], Awaitable[None]] | None = None,
) -> None:
    with ui.row().classes("w-full items-center no-wrap gap-2") as row:
        if item["when"] == "earlier":
            # Past items are greyed out (brand grey: 60% black).
            row.classes("text-grey-7")
        with ui.column().classes("gap-0 grow"):
            moment = local(item["starts_at"]).strftime("%d/%m/%Y")
            line = ui.label(f"{moment} {_hours(item)} · {item['title']}")
            if item["when"] == "today":
                line.classes("font-medium")
            if show_project or (item["kind"] == "deadline" and not item["project_id"]):
                ui.label(_for_whom(item)).classes("text-caption")
            if item["place"]:
                _place(item["place"])
            if item["details"]:
                ui.label(item["details"]).classes("text-caption")
        if change:
            ui.button(icon="edit", on_click=lambda: change(item)).props(
                "flat dense color=dark"
            ).mark(f"edit-{item['kind']}")
        if delete:
            ui.button(icon="delete", on_click=lambda: delete(item)).props(
                "flat dense color=dark"
            ).mark(f"delete-{item['kind']}")


def _item_lists(items: list[Item], row: Callable[[Item], None]) -> None:
    """Upcoming (today first) and, folded away, the earlier ones."""
    coming = [item for item in items if item["when"] != "earlier"]
    earlier = [item for item in items if item["when"] == "earlier"]
    if not coming:
        ui.label("Nothing coming up.").classes("text-caption")
    for item in coming:
        row(item)
    if earlier:
        with ui.expansion(f"Earlier ({len(earlier)})").classes("w-full text-grey-7"):
            for item in reversed(earlier):
                row(item)


def _slot_text(slot: Item) -> str:
    return (
        f"Every {slot['weekday_name']} {slot['starts'][:5]}–{slot['ends'][:5]}"
        f" · {slot['place']}"
    )


def _skipped_text(day: str) -> str:
    return f"Not on {day[8:10]}/{day[5:7]}/{day[:4]}"


def _change_item(after: Callable[[], None]) -> Callable[[Item], Awaitable[None]]:
    async def change(item: Item) -> None:
        if item["kind"] == "deadline":
            fields = await _deadline_dialog(item)
            if fields is not None:
                await _call(
                    api.update_deadline(token(), item["id"], fields),
                    "The deadline was changed.",
                    after,
                )
        else:
            fields = await _meeting_dialog(item)
            if fields is not None:
                await _call(
                    api.update_meeting(token(), item["id"], fields),
                    "The meeting was changed.",
                    after,
                )

    return change


def _delete_item(after: Callable[[], None]) -> Callable[[Item], Awaitable[None]]:
    async def delete(item: Item) -> None:
        what = (
            f"the deadline {item['title']}"
            if item["kind"] == "deadline"
            else (f"the meeting of {_day(item)}")
        )
        if not await confirm(f"Delete {what}?", "Delete"):
            return
        if item["kind"] == "deadline":
            call = api.delete_deadline(token(), item["id"])
        else:
            call = api.delete_meeting(token(), item["id"])
        await _call(call, f"Deleted {what}.", after)

    return delete


async def planning_card(project: dict[str, Any], *, editable: bool) -> None:
    """A Project's deadlines (its own and those for every Project), meetings and
    Weekly slot; Teachers change them while the Project is Active."""
    project_id = project["id"]

    @ui.refreshable
    async def content() -> None:
        planning = await api.project_planning(token(), project_id)
        today_banner(planning["items"], show_project=False)
        slot = planning["weekly_slot"]
        if slot:
            ui.label(_slot_text(slot)).mark("weekly-slot")
            for day in slot["skipped"]:
                with ui.row().classes("items-center gap-1"):
                    ui.label(_skipped_text(day)).classes("text-caption")
                    if editable:
                        ui.button(
                            icon="undo",
                            on_click=lambda d=day: _call(
                                api.unskip_date(token(), project_id, d),
                                "The weekly meeting takes place again that day.",
                                content.refresh,
                            ),
                        ).props("flat dense color=dark").mark("unskip-date")

        def row(item: Item) -> None:
            # Deadlines for every Project are changed on the Planning screen;
            # weekly meetings through the Weekly slot.
            own = (
                editable
                and item["kind"] != "weekly"
                and item["project_id"] == project_id
            )
            _item_row(
                item,
                show_project=False,
                change=_change_item(content.refresh) if own else None,
                delete=_delete_item(content.refresh) if own else None,
            )

        _item_lists(planning["items"], row)
        if editable:
            with ui.row():
                ui.button("Add deadline", on_click=add_deadline).props(
                    "outline color=dark"
                ).mark("add-deadline")
                ui.button("Add meeting", on_click=add_meeting).props(
                    "outline color=dark"
                ).mark("add-meeting")
                ui.button(
                    "Change weekly meeting" if slot else "Set weekly meeting",
                    on_click=lambda: set_slot(slot),
                ).props("outline color=dark").mark("set-slot")
                if slot:
                    ui.button("Skip a date", on_click=lambda: skip(slot)).props(
                        "outline color=dark"
                    ).mark("skip-a-date")
                    ui.button("Clear weekly meeting", on_click=clear_slot).props(
                        "outline color=dark"
                    ).mark("clear-slot")

    async def add_deadline() -> None:
        fields = await _deadline_dialog()
        if fields is not None:
            await _call(
                api.add_deadline(token(), project_id, fields),
                f"The deadline {fields['title']} was added.",
                content.refresh,
            )

    async def add_meeting() -> None:
        fields = await _meeting_dialog()
        if fields is not None:
            await _call(
                api.add_meeting(token(), project_id, fields),
                "The meeting was added.",
                content.refresh,
            )

    async def set_slot(slot: Item | None) -> None:
        fields = await _slot_dialog(slot)
        if fields is not None:
            await _call(
                api.set_weekly_slot(token(), project_id, fields),
                "The weekly meeting was saved.",
                content.refresh,
            )

    async def skip(slot: Item) -> None:
        day = await _skip_dialog(slot)
        if day is not None:
            await _call(
                api.skip_date(token(), project_id, day),
                "No weekly meeting that day.",
                content.refresh,
            )

    async def clear_slot() -> None:
        if await confirm("Clear the weekly meeting?", "Clear"):
            await _call(
                api.clear_weekly_slot(token(), project_id),
                "The weekly meeting was cleared.",
                content.refresh,
            )

    with ui.card().classes("w-full max-w-lg").mark("planning-card"):
        ui.label("Planning").classes("text-h6")
        await content()


async def my_planning_card() -> None:
    """On My project: the Student's Project's planning, read-only."""
    planning = await api.my_planning(token())
    with ui.card().classes("w-full").mark("my-planning"):
        ui.label("Planning").classes("text-h6")
        today_banner(planning["items"], show_project=False)
        if planning["weekly_slot"]:
            ui.label(_slot_text(planning["weekly_slot"])).mark("weekly-slot")
        _item_lists(planning["items"], lambda item: _item_row(item, show_project=False))


SLOT_COLUMNS = [
    {"name": "project", "label": "Project", "field": "project_title", "align": "left"},
    {"name": "day", "label": "Day", "field": "weekday_name", "align": "left"},
    {"name": "time", "label": "Time", "field": "time", "align": "left"},
    {"name": "place", "label": "Place", "field": "place", "align": "left"},
]


def register() -> None:
    @role_page("/planning", "Planning", STAFF)
    async def planning_page(user: api.CurrentUser) -> None:
        @ui.refreshable
        async def content() -> None:
            planning = await api.planning(token(), mine=only_mine.value)
            items = planning["items"]
            today_banner(items, show_project=True)

            def row(item: Item) -> None:
                # Here the deadlines for every Project are changed.
                for_all = item["kind"] == "deadline" and item["project_id"] is None
                _item_row(
                    item,
                    show_project=True,
                    change=_change_item(content.refresh) if for_all else None,
                    delete=_delete_item(content.refresh) if for_all else None,
                )

            if not items:
                ui.label("Nothing coming up.")
            for day, on_day in groupby(items, key=_day):
                ui.label(day).classes("text-subtitle1 font-medium q-mt-md")
                for item in on_day:
                    row(item)
            ui.label("Weekly meetings").classes("text-h6 q-mt-lg")
            rows = [
                slot | {"time": f"{slot['starts'][:5]}–{slot['ends'][:5]}"}
                for slot in planning["weekly_slots"]
            ]
            ui.table(columns=SLOT_COLUMNS, rows=rows, row_key="project_id").classes(
                "w-full"
            ).mark("weekly-slots")

        async def add_for_all() -> None:
            fields = await _deadline_dialog()
            if fields is not None:
                await _call(
                    api.add_deadline(token(), None, fields),
                    f"The deadline {fields['title']} was added for all Projects.",
                    content.refresh,
                )

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
