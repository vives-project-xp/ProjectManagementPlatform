"""A Project's cover photo. The browser has no API token (it stays in this
server's user storage), so photos reach it through a frontend route that fetches
them over the REST API (ADR 0003)."""

from collections.abc import Awaitable
from typing import Any

from nicegui import app, events, ui
from starlette.responses import Response

from pmp_frontend import api
from pmp_frontend.shell import ErrorMessage, confirm, token

MAX_BYTES = 5 * 1024 * 1024
# Greys from the house style: 20% black behind a 60% black icon.
PLACEHOLDER_STYLE = "background: #cccccc; color: #666666"

# The Projects table's thumbnail column, with the same placeholder.
THUMBNAIL_CELL = (
    """
<q-td :props="props">
  <img v-if="props.value" :src="props.value" alt=""
       style="width: 64px; height: 40px; object-fit: cover; border-radius: 4px" />
  <div v-else class="flex flex-center"
       style="width: 64px; height: 40px; border-radius: 4px; """
    + PLACEHOLDER_STYLE
    + """">
    <q-icon name="image" />
  </div>
</q-td>
"""
)


def photo_url(project_id: int, version: int | None) -> str | None:
    """Where the browser gets the photo; the version busts caches after an upload."""
    if version is None:
        return None
    return f"/photos/{project_id}?v={version}"


def show_photo(project_id: int, version: int | None) -> None:
    """The photo, or a neutral placeholder when the Project has none."""
    url = photo_url(project_id, version)
    if url is None:
        with (
            ui.element("div")
            .classes("w-full max-w-lg h-48 flex flex-center rounded-borders")
            .style(PLACEHOLDER_STYLE)
            .mark("photo-placeholder")
        ):
            ui.icon("image", size="xl")
    else:
        ui.image(url).classes("w-full max-w-lg rounded-borders").mark("project-photo")


def photo_card(project: dict[str, Any], *, editable: bool) -> None:
    """The photo on a Project's details page; with upload and remove when editable
    (Archived Projects keep their photo, read-only)."""
    project_id = project["id"]

    async def change(call: Awaitable[Any]) -> None:
        """Run the API call; reload the page, or show why it was refused."""
        try:
            await call
        except api.ApiError as error:
            photo_error.show(error.message)
            return
        ui.navigate.to(f"/projects/{project_id}")

    async def upload(event: events.UploadEventArguments) -> None:
        file = event.file
        data = await file.read()
        await change(
            api.upload_photo(token(), project_id, file.name, data, file.content_type)
        )

    async def remove() -> None:
        if await confirm(f"Remove the photo of {project['title']}?", "Remove"):
            await change(api.remove_photo(token(), project_id))

    with ui.card().classes("w-full max-w-lg"):
        ui.label("Photo").classes("text-h6")
        show_photo(project_id, project["photo_version"])
        photo_error = ErrorMessage()
        if not editable:
            return
        ui.upload(
            label="Upload a photo (JPG or PNG, at most 5 MB)",
            auto_upload=True,
            max_file_size=MAX_BYTES,
            on_upload=upload,
            # Rejected for its type or its size; the browser does not say which.
            on_rejected=lambda: photo_error.show(
                "Only JPG and PNG photos up to 5 MB are accepted."
            ),
        ).props('accept=".jpg,.jpeg,.png" flat bordered').classes("w-full").mark(
            "photo-upload"
        )
        if project["photo_version"] is not None:
            ui.button("Remove photo", on_click=remove).props("outline color=dark").mark(
                "remove-photo"
            )


def register() -> None:
    @app.get("/photos/{project_id}")
    async def photo(project_id: int) -> Response:
        if not token():
            return Response(status_code=401)
        try:
            data, media_type = await api.project_photo(token(), project_id)
        except api.ApiError as error:
            return Response(status_code=error.status_code)
        # The URL carries the photo's version, so the browser may keep it a while.
        return Response(
            data,
            media_type=media_type,
            headers={"Cache-Control": "private, max-age=86400"},
        )
