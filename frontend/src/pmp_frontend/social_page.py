"""Social media (spec #110): the Superuser's settings, the Members' Weekly
update and the Weekly updates on a Project's page."""

from collections.abc import Callable
from typing import Any

from nicegui import app, events, ui
from starlette.responses import Response

from pmp_frontend import api
from pmp_frontend.shell import ErrorMessage, confirm, role_page, token
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
MAX_PHOTOS = 5
MAX_PHOTO_BYTES = 15 * 1024 * 1024
PHOTO_TYPES = ".jpg,.jpeg,.png,.heic,.heif"
CONSENT = (
    "Everyone recognisable in these photos agrees to them being posted on VIVES "
    "social media."
)


def medium_url(medium: dict[str, Any]) -> str:
    return f"/weekly-media/{medium['id']}"


def _media_grid(
    media: list[dict[str, Any]], on_remove: Callable[[dict], Any] | None = None
) -> None:
    """Thumbnails with who uploaded them; with Remove while the week is open."""
    with ui.row().classes("w-full gap-3"):
        for medium in media:
            with ui.column().classes("gap-1").mark(f"medium-{medium['id']}"):
                ui.image(medium_url(medium)).props("fit=cover").classes(
                    "w-40 h-28 rounded-borders"
                )
                ui.label(medium["uploaded_by"]).classes("text-caption")
                if on_remove is not None:
                    ui.button("Remove", on_click=lambda m=medium: on_remove(m)).props(
                        "flat dense color=dark"
                    ).mark(f"remove-medium-{medium['id']}")


def _week_text(week: dict[str, Any]) -> str:
    return week["text"] or "Nothing was written."


def _edited(week: dict[str, Any]) -> str:
    if week["edited_at"] is None:
        return "Nobody has written anything yet."
    return f"Last edited by {week['edited_by']} on {shown(week['edited_at'])}."


def _earlier_weeks(weeks: list[dict[str, Any]]) -> None:
    for week in weeks:
        with ui.card().classes("w-full max-w-2xl").mark("earlier-week"):
            ui.label(f"Upload week until {shown(week['closes_at'])}").classes(
                "font-medium"
            )
            ui.label(_week_text(week)).classes("whitespace-pre-wrap")
            _media_grid(week["media"])
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
                _media_grid(week["media"])
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


def _photos_card(media: list[dict[str, Any]]) -> None:
    """Upload, see and remove the team's photos of the open Upload week."""

    @ui.refreshable
    def photos(media: list[dict[str, Any]]) -> None:
        count = sum(1 for medium in media if medium["kind"] == "photo")
        ui.label(f"{count} of {MAX_PHOTOS} photos").mark("photo-count")
        _media_grid(media, on_remove=remove)

    def show(mine: dict[str, Any]) -> None:
        photos.refresh(mine["current"]["media"])

    async def upload(event: events.UploadEventArguments) -> None:
        file = event.file
        try:
            mine = await api.upload_weekly_photo(
                token(),
                file.name,
                await file.read(),
                file.content_type,
                consent=bool(consent.value),
            )
        except api.ApiError as problem:
            error.show(f"{file.name}: {problem.message}")
            return
        error.hide()
        show(mine)

    async def remove(medium: dict[str, Any]) -> None:
        if not await confirm("Remove this photo?", "Remove"):
            return
        try:
            show(await api.remove_weekly_medium(token(), medium["id"]))
        except api.ApiError as problem:
            error.show(problem.message)

    with ui.column().classes("w-full gap-2").mark("photos"):
        ui.label("Photos").classes("text-h6")
        ui.label(
            f"Up to {MAX_PHOTOS} photos: JPG, PNG or HEIC, at most 15 MB, the short "
            "side at least 1080 pixels. Blurry, dark or overexposed photos are "
            "refused straight away."
        ).classes("text-caption")
        consent = ui.checkbox(CONSENT).mark("consent")
        ui.upload(
            label="Upload photos",
            multiple=True,
            auto_upload=True,
            max_file_size=MAX_PHOTO_BYTES,
            on_upload=upload,
            on_rejected=lambda: error.show(
                "Only JPG, PNG and HEIC photos up to 15 MB are accepted."
            ),
        ).props(f'accept="{PHOTO_TYPES}" flat bordered').classes(
            "w-full"
        ).bind_enabled_from(consent, "value").mark("photo-upload")
        error = ErrorMessage()
        photos(media)


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
        if current is not None:
            _photos_card(current["media"])
    if mine["earlier"]:
        ui.label("Earlier weeks").classes("text-h6")
        _earlier_weeks(mine["earlier"])


def register() -> None:
    @app.get("/weekly-media/{medium_id}")
    async def weekly_medium(medium_id: int) -> Response:
        """A Weekly update's photo or video, fetched with the User's token."""
        if not token():
            return Response(status_code=401)
        try:
            found = await api.weekly_medium(token(), medium_id)
        except api.ApiError as error:
            return Response(status_code=error.status_code)
        # A medium never changes once uploaded, so the browser may keep it a while.
        return Response(
            found.content,
            media_type=found.headers["content-type"],
            headers={"Cache-Control": "private, max-age=86400"},
        )

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
