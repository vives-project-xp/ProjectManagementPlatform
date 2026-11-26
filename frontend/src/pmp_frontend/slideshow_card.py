"""The Weekly slideshow's Review (spec #145, #149): at the top of Post
suggestions, any Teacher or the Superuser checks the photos (swap one for
another photo of its Project, remove, move), edits the AI's title and caption
or writes them, lets the AI start over, or refuses it."""

from typing import Any

from nicegui import app, ui
from starlette.responses import Response

from pmp_frontend import api
from pmp_frontend.shell import ErrorMessage, SaveButton, confirm, token
from pmp_frontend.social_page import medium_url
from pmp_frontend.times import shown

STATES = {
    "generating": ("Being written", "grey-7"),
    "waiting": ("Waiting for Review", "primary"),
    "failed": ("Write it yourself", "primary"),
    "refused": ("Refused", "grey-7"),
    "none": ("No slideshow", "grey-7"),
    "scheduled": ("Scheduled", "positive"),
    "in_inbox": ("In the TikTok app", "primary"),
    "to_post_by_hand": ("To post by hand", "primary"),
    "posted": ("Posted", "positive"),
    "dropped": ("Not posted in time", "grey-7"),
}
SONG_CHECK = "I listened to the song and posted it in the TikTok app"
MAX_TITLE = 90


class SlideshowCard:
    """The latest Weekly slideshow and what its state allows."""

    def __init__(self, slideshow: dict[str, Any], reload) -> None:
        self.slideshow = slideshow
        self.reload = reload
        label, colour = STATES.get(slideshow["state"], (slideshow["state"], "grey-7"))
        with ui.card().classes("w-full max-w-3xl").mark("slideshow-card"):
            with ui.row().classes("w-full items-center"):
                ui.icon("collections", color="dark")
                ui.label("Weekly slideshow").classes("text-h6")
                ui.label(f"Upload week until {shown(slideshow['closes_at'])}").classes(
                    "text-caption"
                )
                ui.space()
                ui.badge(label, color=colour).mark("slideshow-state")
            self.error = ErrorMessage()
            getattr(self, f"_{slideshow['state']}", self._other)()

    @property
    def _id(self) -> int:
        return self.slideshow["id"]

    def _generating(self) -> None:
        with ui.row().classes("items-center gap-2"):
            ui.spinner(color="dark")
            ui.label("The AI is writing the slideshow's text…")
        self._photos(editable=False)

    def _none(self) -> None:
        ui.label(
            "No Project with a photo was Posted this week, so there is no slideshow. "
            "Generate again once one is Posted."
        ).mark("slideshow-none")
        self._generate_button()

    def _refused(self) -> None:
        reason = self.slideshow["refusal_reason"]
        ui.label("No slideshow this week" + (f": {reason}" if reason else ".")).mark(
            "slideshow-refused"
        )

    def _other(self) -> None:
        self._photos(editable=False)

    # Posting (#150)

    def _scheduled(self) -> None:
        ui.label(
            "Goes to the TikTok app on "
            f"{shown(self.slideshow['scheduled_for'])}; you can pull it back "
            "until then."
        ).mark("slideshow-scheduled")
        if self.slideshow["publish_error"]:
            self._problem(self.slideshow["publish_error"])
        self._photos(editable=False)
        self._text()
        ui.button("Pull back", icon="undo", on_click=self._pull_back).props(
            "outline color=dark"
        ).mark("pull-back-slideshow")

    def _in_inbox(self) -> None:
        ui.label(
            "In the TikTok app: choose the song. Open TikTok on the VIVES account, "
            "find the slideshow in your inbox, pick and listen to a song, post it, "
            "then press Posted here."
        ).mark("slideshow-in-inbox")
        self._photos(editable=False)
        self._text()
        self._finish()

    def _to_post_by_hand(self) -> None:
        ui.label(
            "Post it yourself: download the photos, copy the caption, make a photo "
            "post in the TikTok app with a song, then press Posted here."
        ).mark("slideshow-by-hand")
        if self.slideshow["publish_error"]:
            self._problem(self.slideshow["publish_error"])
        self._photos(editable=False)
        self._text()
        with ui.row().classes("items-center gap-2"):
            ui.button(
                "Download photos",
                icon="download",
                on_click=lambda: ui.download(f"/slideshow-photos/{self._id}.zip"),
            ).props("outline color=dark").mark("download-slideshow")
            ui.button("Copy caption", icon="content_copy", on_click=self._copy).props(
                "outline color=dark"
            ).mark("copy-slideshow-caption")
        self._finish()

    def _posted(self) -> None:
        ui.label(
            f"Posted by {self.slideshow['posted_by']} on "
            f"{shown(self.slideshow['posted_at'])}."
        ).mark("slideshow-posted")
        self._photos(editable=False)

    def _dropped(self) -> None:
        ui.label(self.slideshow["publish_error"] or "Not posted in time.").mark(
            "slideshow-dropped"
        )

    def _problem(self, text: str) -> None:
        with ui.row().classes("items-center gap-2 no-wrap").mark("slideshow-problem"):
            ui.icon("warning", color="primary")
            ui.label(text)

    def _text(self) -> None:
        with ui.column().classes("gap-1"):
            ui.label(self.slideshow["title"] or "").classes("font-medium")
            ui.label(self.slideshow["caption"] or "").classes("whitespace-pre-wrap")

    def _copy(self) -> None:
        ui.clipboard.write(f"{self.slideshow['title']}\n\n{self.slideshow['caption']}")
        ui.notify("The caption was copied.")

    def _finish(self) -> None:
        """The Song check, then Posted (only once ticked)."""
        check = ui.checkbox(SONG_CHECK).mark("song-check")
        ui.button(
            "Posted", icon="done", on_click=lambda: self._mark_posted(check.value)
        ).bind_enabled_from(check, "value").mark("mark-slideshow-posted")

    async def _mark_posted(self, checked: bool) -> None:
        try:
            await api.mark_slideshow_posted(token(), self._id, bool(checked))
        except api.ApiError as problem:
            self.error.show(problem.message)
            return
        ui.notify("The slideshow is marked as posted.")
        await self.reload()

    async def _post(self) -> None:
        question = (
            "Post the slideshow? It goes to TikTok at its Posting time (or within a "
            "minute when that has passed); you can pull it back until then."
        )
        if not await confirm(question, "Post"):
            return
        try:
            done = await api.post_slideshow(token(), self._id)
        except api.ApiError as problem:
            self.error.show(problem.message)
            return
        ui.notify(f"The slideshow goes out on {shown(done['scheduled_for'])}.")
        await self.reload()

    async def _pull_back(self) -> None:
        try:
            await api.pull_back_slideshow(token(), self._id)
        except api.ApiError as problem:
            self.error.show(problem.message)
            return
        ui.notify("The slideshow was pulled back to Review.")
        await self.reload()

    def _failed(self) -> None:
        ui.label(
            "The AI couldn't write the text"
            + (
                f" ({self.slideshow['last_error']})"
                if self.slideshow["last_error"]
                else ""
            )
            + ": write it yourself, or let it try again."
        ).mark("slideshow-failed")
        self._waiting()

    def _waiting(self) -> None:
        self._photos(editable=True)
        self._editor()

    # The photos

    def _ids(self) -> list[int]:
        return [photo["medium"]["id"] for photo in self.slideshow["photos"]]

    async def _save_photos(self, ids: list[int]) -> None:
        try:
            await api.set_slideshow_photos(token(), self._id, ids)
        except api.ApiError as problem:
            self.error.show(problem.message)
            return
        await self.reload()

    async def _move(self, index: int, step: int) -> None:
        ids = self._ids()
        ids[index], ids[index + step] = ids[index + step], ids[index]
        await self._save_photos(ids)

    async def _remove(self, index: int) -> None:
        ids = self._ids()
        del ids[index]
        await self._save_photos(ids)

    def _other_photos(self, photo: dict[str, Any]) -> list[int]:
        """The Project's photos that aren't in the slideshow yet."""
        used = set(self._ids())
        project = next(
            (
                p
                for p in self.slideshow["projects"]
                if p["project"]["id"] == photo["project"]["id"]
            ),
            None,
        )
        if project is None:
            return []
        return [m["id"] for m in project["photos"] if m["id"] not in used]

    async def _swap(self, index: int) -> None:
        ids = self._ids()
        others = self._other_photos(self.slideshow["photos"][index])
        if not others:
            return
        ids[index] = others[0]
        await self._save_photos(ids)

    def _photos(self, *, editable: bool) -> None:
        photos = self.slideshow["photos"]
        with ui.row().classes("w-full gap-3"):
            for index, photo in enumerate(photos):
                medium = photo["medium"]
                with (
                    ui.column()
                    .classes("gap-1 items-center")
                    .mark(f"slideshow-photo-{medium['id']}")
                ):
                    ui.label(f"{index + 1}").classes("font-medium")
                    ui.image(medium_url(medium)).props("fit=cover").classes(
                        "w-32 h-40 rounded-borders"
                    )
                    ui.label(photo["project"]["title"]).classes("text-caption")
                    if editable:
                        self._photo_buttons(index, photo, len(photos))

    def _photo_buttons(self, index: int, photo: dict[str, Any], count: int) -> None:
        medium_id = photo["medium"]["id"]
        with ui.row().classes("gap-0"):
            if index > 0:
                ui.button(
                    icon="chevron_left", on_click=lambda i=index: self._move(i, -1)
                ).props("flat dense color=dark").tooltip("Earlier").mark(
                    f"slideshow-left-{medium_id}"
                )
            if index < count - 1:
                ui.button(
                    icon="chevron_right", on_click=lambda i=index: self._move(i, 1)
                ).props("flat dense color=dark").tooltip("Later").mark(
                    f"slideshow-right-{medium_id}"
                )
            if self._other_photos(photo):
                ui.button(
                    icon="swap_horiz", on_click=lambda i=index: self._swap(i)
                ).props("flat dense color=dark").tooltip(
                    "Another photo of this Project"
                ).mark(f"slideshow-swap-{medium_id}")
            if count > 1:
                ui.button(icon="close", on_click=lambda i=index: self._remove(i)).props(
                    "flat dense color=dark"
                ).tooltip("Remove").mark(f"slideshow-remove-{medium_id}")

    # The text

    def _editor(self) -> None:
        slideshow = self.slideshow
        title = (
            ui.input(
                f"Title (at most {MAX_TITLE} characters)",
                value=slideshow["title"] or "",
            )
            .props(f"counter maxlength={MAX_TITLE}")
            .classes("w-full")
            .mark("slideshow-title")
        )
        caption = (
            ui.textarea("Caption", value=slideshow["caption"] or "")
            .props("autogrow counter")
            .classes("w-full")
            .mark("slideshow-caption")
        )

        async def save() -> None:
            try:
                await api.edit_slideshow(
                    token(), self._id, title.value or "", caption.value or ""
                )
            except api.ApiError as problem:
                self.error.show(problem.message)
                return
            ui.notify("The slideshow was saved.")
            await self.reload()

        if slideshow["reviewed_at"]:
            ui.label(
                f"Last changed by {slideshow['reviewed_by']} on "
                f"{shown(slideshow['reviewed_at'])}."
            ).classes("text-caption")
        with ui.row().classes("items-center gap-2"):
            save_button = SaveButton([title, caption], save)
            save_button.button.mark("save-slideshow")
            if slideshow["state"] == "waiting":
                # What is posted is what is saved: save changes first.
                ui.button("Post", icon="send", on_click=self._post).bind_enabled_from(
                    save_button.button, "enabled", backward=lambda unsaved: not unsaved
                ).mark("post-slideshow")
            ui.button("Refuse", on_click=self._refuse).props("outline color=dark").mark(
                "refuse-slideshow"
            )
            self._generate_button()

    def _generate_button(self) -> None:
        ui.button("Generate again", icon="auto_awesome", on_click=self._generate).props(
            "flat color=dark"
        ).mark("generate-slideshow")

    async def _generate(self) -> None:
        question = (
            "Put the slideshow together again (with the Projects Posted since) and "
            "let the AI write it again? Your changes are lost."
        )
        if not await confirm(question, "Generate again"):
            return
        try:
            await api.generate_slideshow(token(), self._id)
        except api.ApiError as problem:
            self.error.show(problem.message)
            return
        await self.reload()

    async def _refuse(self) -> None:
        with ui.dialog() as dialog, ui.card().classes("w-full max-w-md"):
            ui.label("Refuse the slideshow? There will be none this week.")
            reason = ui.input("Reason (optional)").classes("w-full")
            reason.mark("slideshow-refusal-reason")
            with ui.row():
                ui.button("Refuse", on_click=lambda: dialog.submit(True)).mark(
                    "confirm-slideshow-refusal"
                )
                ui.button("Cancel", on_click=lambda: dialog.submit(False)).props(
                    "flat color=dark"
                )
        sure = await dialog
        dialog.delete()
        if not sure:
            return
        try:
            await api.refuse_slideshow(token(), self._id, reason.value or None)
        except api.ApiError as problem:
            self.error.show(problem.message)
            return
        ui.notify("The slideshow was refused.")
        await self.reload()


def register() -> None:
    @app.get("/slideshow-photos/{slideshow_id}.zip")
    async def slideshow_photos(slideshow_id: int) -> Response:
        """The Weekly slideshow's photos as one zip, fetched with the User's
        token (#150)."""
        if not token():
            return Response(status_code=401)
        try:
            found = await api.slideshow_zip(token(), slideshow_id)
        except api.ApiError as error:
            return Response(status_code=error.status_code)
        return Response(
            found.content,
            media_type="application/zip",
            headers={
                "Content-Disposition": found.headers["content-disposition"],
                "Cache-Control": "no-store",
            },
        )
