"""Social media (spec #110): the Superuser's settings, the Members' Weekly
update and the Weekly updates on a Project's page."""

from typing import Any

from nicegui import ui

from pmp_frontend import api
from pmp_frontend.shell import ErrorMessage, role_page, token
from pmp_frontend.times import shown

WEEKDAYS = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]
MAX_UPDATE_LENGTH = 4000


def _week_text(week: dict[str, Any]) -> str:
    return week["text"] or "Nothing was written."


def _edited(week: dict[str, Any]) -> str:
    if week["edited_at"] is None:
        return "Nobody has written anything yet."
    return f"Last edited by {week['edited_by']} on {shown(week['edited_at'])}."


def _earlier_weeks(weeks: list[dict[str, Any]]) -> None:
    for week in weeks:
        with ui.card().classes("w-full").mark("earlier-week"):
            ui.label(f"Upload week until {shown(week['closes_at'])}").classes(
                "font-medium"
            )
            ui.label(_week_text(week)).classes("whitespace-pre-wrap")
            ui.label(_edited(week)).classes("text-caption")


async def weekly_updates_card(project_id: int) -> None:
    """A Project's Weekly updates for Teachers and the Superuser, newest first."""
    weeks = await api.project_weekly_updates(token(), project_id)
    with ui.card().classes("w-full max-w-lg").mark("weekly-updates-card"):
        ui.label("Weekly updates").classes("text-h6")
        if not weeks:
            ui.label("No Weekly updates yet.")
            return
        for week in weeks:
            state = "open" if week["is_open"] else "closed"
            with ui.expansion(
                f"Until {shown(week['closes_at'])} ({state})", value=week is weeks[0]
            ).classes("w-full"):
                ui.label(_week_text(week)).classes("whitespace-pre-wrap")
                ui.label(_edited(week)).classes("text-caption")


def _settings_form(settings: dict[str, Any]) -> None:
    async def save() -> None:
        body = {
            "upload_weekday": weekday.value,
            "upload_time": deadline_time.value or None,
            "instagram_weekdays": sorted(posting_days.value or []),
            "instagram_times": [t for t in (first.value, second.value) if t],
            "fixed_hashtags": hashtags.value or "",
        }
        try:
            await api.set_social_settings(token(), body)
        except api.ApiError as problem:
            error.show(problem.message)
            return
        error.hide()
        ui.notify("The social media settings were saved.")

    days = dict(enumerate(WEEKDAYS))
    with ui.card().classes("w-full max-w-lg"):
        ui.label("Upload deadline").classes("text-h6")
        ui.label(
            "Every Project's Weekly update closes at this moment (Belgian time). "
            "A changed deadline closes the open Upload week at the next matching "
            "moment."
        ).classes("text-caption")
        weekday = ui.select(days, value=settings["upload_weekday"], label="Weekday")
        weekday.classes("w-full").mark("upload-weekday")
        deadline_time = ui.input("Time (HH:MM)", value=settings["upload_time"] or "")
        deadline_time.mark("upload-time")
    with ui.card().classes("w-full max-w-lg"):
        ui.label("Instagram Posting times").classes("text-h6")
        posting_days = (
            ui.select(
                days,
                value=settings["instagram_weekdays"],
                label="Weekdays",
                multiple=True,
            )
            .classes("w-full")
            .mark("instagram-weekdays")
        )
        times = settings["instagram_times"] + ["", ""]
        with ui.row():
            first = ui.input("Time 1 (HH:MM)", value=times[0]).mark("instagram-time-1")
            second = ui.input("Time 2 (HH:MM)", value=times[1]).mark("instagram-time-2")
    with ui.card().classes("w-full max-w-lg"):
        ui.label("Fixed hashtags").classes("text-h6")
        ui.label("Every caption carries these.").classes("text-caption")
        hashtags = ui.input("Hashtags", value=settings["fixed_hashtags"])
        hashtags.classes("w-full").mark("fixed-hashtags")
    error = ErrorMessage()
    ui.button("Save", on_click=save).mark("save-social-settings")


def _weekly_update_page(mine: dict[str, Any]) -> None:
    current = mine["current"]

    async def save() -> None:
        try:
            await api.save_weekly_update(token(), editor.value or "")
        except api.ApiError as problem:
            error.show(problem.message)
            return
        ui.notify("The Weekly update was saved.")
        ui.navigate.to("/weekly-update")

    ui.label(mine["project"]["title"]).classes("text-h6")
    with ui.card().classes("w-full max-w-2xl").mark("current-week"):
        if current is None:
            ui.label("The Upload deadline hasn't been set yet. Check back later.")
        else:
            ui.label(
                f"This Upload week closes on {shown(current['closes_at'])} "
                "(Belgian time). Until then, every Member can edit it."
            )
            editor = (
                ui.textarea(
                    "What did your team do this week?",
                    value=current["text"],
                    validation={
                        "Too long": lambda value: len(value or "") <= MAX_UPDATE_LENGTH
                    },
                )
                .props(f"counter maxlength={MAX_UPDATE_LENGTH} autogrow")
                .classes("w-full")
                .mark("weekly-update-text")
            )
            ui.label(_edited(current)).classes("text-caption")
            error = ErrorMessage()
            ui.button("Save", on_click=save).mark("save-weekly-update")
    if mine["earlier"]:
        ui.label("Earlier weeks").classes("text-h6")
        _earlier_weeks(mine["earlier"])


def register() -> None:
    @role_page("/social-media", "Social media", {"superuser"})
    async def settings_page(user: api.CurrentUser) -> None:
        _settings_form(await api.social_settings(token()))

    @role_page("/weekly-update", "Weekly update", {"student"})
    async def weekly_update_page(user: api.CurrentUser) -> None:
        mine = await api.my_weekly_update(token())
        if mine is None:
            ui.label("You're not in a Project yet.")
            return
        _weekly_update_page(mine)
