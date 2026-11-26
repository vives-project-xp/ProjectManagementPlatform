"""Post suggestions and their Review (spec #110, #115): Teachers and the
Superuser edit the AI's suggestion, pick another photo or the video, refuse it,
let the AI start over, or write the post themselves when the AI couldn't."""

from typing import Any

from nicegui import ui

from pmp_frontend import api
from pmp_frontend.shell import ErrorMessage, SaveButton, confirm, role_page, token
from pmp_frontend.slideshow_card import SlideshowCard
from pmp_frontend.social_page import media_grid
from pmp_frontend.times import shown

STATES = {
    "generating": ("Being written", "grey-7"),
    "waiting": ("Waiting for Review", "primary"),
    "failed": ("No suggestion", "grey-7"),
    "refused": ("Refused", "grey-7"),
    "scheduled": ("Scheduled", "positive"),
    "to_post_by_hand": ("To post by hand", "primary"),
    "posted_by_hand": ("Posted", "positive"),
}
# How often the page looks again while the AI is writing.
GENERATING_SECONDS = 5.0
TIKTOK_STATES = {
    "scheduled": "scheduled for {when}",
    "published": "published on {posted}",
    "to_post_by_hand": "to post by hand (its Posting time has come)",
    "posted_by_hand": "posted by hand on {posted}",
}
MUSIC_USAGE = "https://www.tiktok.com/legal/page/global/music-usage-confirmation/en"


def tiktok_text(post: dict[str, Any]) -> str:
    """Where the suggestion's TikTok video stands, e.g. "scheduled for …"."""
    return TIKTOK_STATES.get(post["state"], post["state"]).format(
        when=shown(post["scheduled_for"]) if post["scheduled_for"] else "",
        posted=shown(post["posted_at"]) if post["posted_at"] else "",
    )


def _medium_options(suggestion: dict[str, Any]) -> dict[int, str]:
    """The photos and video to choose from, numbered as on the thumbnails."""
    return {
        medium["id"]: f"{number}. {medium['kind'].capitalize()} by "
        f"{medium['uploaded_by']}"
        for number, medium in enumerate(suggestion["ranking"], start=1)
    }


def _numbered(media: list[dict[str, Any]]) -> None:
    with ui.row().classes("w-full gap-3"):
        for number, medium in enumerate(media, start=1):
            with ui.column().classes("gap-0 items-center"):
                media_grid([medium])
                ui.label(f"{number}").classes("font-medium")


class SuggestionCard:
    """One Post suggestion and the Review actions its state allows."""

    def __init__(
        self,
        suggestion: dict[str, Any],
        reload,
        creator: dict[str, Any] | None = None,
    ) -> None:
        self.suggestion = suggestion
        self.reload = reload
        # TikTok's choices for this account (#147); no tick without them.
        self.creator = creator
        self.tiktok: dict[str, Any] | None = None
        label, colour = STATES.get(
            suggestion["state"], (suggestion["state"].capitalize(), "grey-7")
        )
        with (
            ui.card().classes("w-full max-w-3xl").mark(f"suggestion-{suggestion['id']}")
        ):
            with ui.row().classes("w-full items-center"):
                ui.label(suggestion["project"]["title"]).classes("text-h6")
                ui.label(f"Upload week until {shown(suggestion['closes_at'])}").classes(
                    "text-caption"
                )
                ui.space()
                ui.badge(label, color=colour).mark("suggestion-state")
            self.error = ErrorMessage()
            getattr(self, f"_{suggestion['state']}", self._other)()
            if suggestion["tiktok"]:
                self._tiktok_line(suggestion["tiktok"])

    def _tiktok_line(self, post: dict[str, Any]) -> None:
        with ui.row().classes("items-center gap-2").mark("tiktok-line"):
            ui.icon("music_note", color="dark")
            ui.label(f"Also on TikTok: {tiktok_text(post)}.").mark("tiktok-state")
            if post["state"] == "scheduled":
                ui.button(
                    "Pull back from TikTok",
                    icon="undo",
                    on_click=self._pull_back_tiktok,
                ).props("flat dense color=dark").mark("pull-back-tiktok")

    async def _pull_back_tiktok(self) -> None:
        try:
            await api.pull_back_tiktok(token(), self._id)
        except api.ApiError as problem:
            self.error.show(problem.message)
            return
        ui.notify("The video was taken off TikTok's line.")
        await self.reload()

    def _tiktok_choices(self) -> None:
        """Also on TikTok (#147): the tick, and then who can see it (TikTok's
        options, no default), the interaction switches and TikTok's notice."""
        creator = self.creator
        tick = ui.checkbox("Also on TikTok (the video)").mark("also-on-tiktok")
        with ui.column().classes("gap-1 pl-8").bind_visibility_from(tick, "value"):
            if not creator["connected"]:
                ui.label(
                    "TikTok isn't connected: the video will come to To post today."
                ).classes("text-caption")
            privacy = (
                ui.select(creator["privacy_levels"], label="Who can see it")
                .classes("w-64")
                .mark("tiktok-privacy")
            )
            comment = ui.switch("Allow comments", value=not creator["comment_disabled"])
            comment.mark("tiktok-comment")
            duet = ui.switch("Allow Duet", value=False).mark("tiktok-duet")
            stitch = ui.switch("Allow Stitch", value=False).mark("tiktok-stitch")
            for switch, off in (
                (comment, creator["comment_disabled"]),
                (duet, creator["duet_disabled"]),
                (stitch, creator["stitch_disabled"]),
            ):
                if off:
                    switch.set_value(False)
                    switch.disable()
            with ui.row().classes("items-center gap-1 text-caption"):
                ui.label("By posting, you agree to TikTok's")
                ui.link("Music Usage Confirmation", MUSIC_USAGE, new_tab=True)
        self.tiktok = {
            "tick": tick,
            "privacy": privacy,
            "comment": comment,
            "duet": duet,
            "stitch": stitch,
        }

    def _tiktok_body(self) -> dict[str, Any] | None:
        """The Post's TikTok part, or None without the tick; raises ValueError
        when who can see it wasn't chosen."""
        if self.tiktok is None or not self.tiktok["tick"].value:
            return None
        if not self.tiktok["privacy"].value:
            raise ValueError("Choose who can see the video on TikTok.")
        return {
            "also_on_tiktok": True,
            "privacy_level": self.tiktok["privacy"].value,
            "allow_comment": bool(self.tiktok["comment"].value),
            "allow_duet": bool(self.tiktok["duet"].value),
            "allow_stitch": bool(self.tiktok["stitch"].value),
        }

    @property
    def _id(self) -> int:
        return self.suggestion["id"]

    def _reviewed(self) -> None:
        if self.suggestion["reviewed_at"]:
            ui.label(
                f"Last reviewed by {self.suggestion['reviewed_by']} on "
                f"{shown(self.suggestion['reviewed_at'])}."
            ).classes("text-caption")

    def _generating(self) -> None:
        with ui.row().classes("items-center gap-2"):
            ui.spinner(color="dark")
            ui.label("The AI is writing this suggestion.")
        if self.suggestion["attempts"]:
            ui.label(
                f"Try {self.suggestion['attempts']} of 3 didn't work "
                f"({self.suggestion['last_error']}); it tries again soon."
            ).classes("text-caption")

    def _waiting(self) -> None:
        if self.suggestion["why"]:
            ui.label(f"Why the AI chose this: {self.suggestion['why']}").classes(
                "text-caption"
            )
        self._editor()

    def _failed(self) -> None:
        ui.label("The AI couldn't make a suggestion.").mark("suggestion-failed")
        ui.label(self.suggestion["last_error"] or "").classes("text-caption")
        ui.label("Write it yourself, let the AI try again, or refuse it.")
        self._editor()

    def _refused(self) -> None:
        reason = self.suggestion["refusal_reason"]
        ui.label(
            "No post for this Project this week" + (f": {reason}" if reason else ".")
        ).mark("refused-reason")
        self._reviewed()
        with ui.row():
            self._generate_button()

    def _scheduled(self) -> None:
        ui.label(
            f"Scheduled for {shown(self.suggestion['scheduled_for'])} on Instagram."
        ).mark("scheduled-for")
        self._post_preview()
        self._reviewed()
        ui.button("Pull back", icon="undo", on_click=self._pull_back).props(
            "outline color=dark"
        ).mark("pull-back")

    def _to_post_by_hand(self) -> None:
        ui.label(
            f"Its Posting time ({shown(self.suggestion['scheduled_for'])}) has "
            "come: publish it from "
        ).mark("to-post")
        ui.link("Scheduled posts", "/scheduled-posts")
        self._post_preview()

    def _posted_by_hand(self) -> None:
        ui.label(
            f"Posted by {self.suggestion['posted_by']} on "
            f"{shown(self.suggestion['posted_at'])}."
        ).mark("posted")
        self._post_preview()

    def _other(self) -> None:
        self._reviewed()

    def _post_preview(self) -> None:
        with ui.row().classes("w-full gap-4 items-start no-wrap"):
            if self.suggestion["chosen"]:
                media_grid([self.suggestion["chosen"]])
            with ui.column().classes("gap-1 min-w-0"):
                ui.label(self.suggestion["title"] or "").classes("font-medium")
                ui.label(self.suggestion["caption"] or "").classes(
                    "whitespace-pre-wrap"
                )

    async def _post(self) -> None:
        try:
            tiktok = self._tiktok_body()
        except ValueError as problem:
            self.error.show(str(problem))
            return
        question = (
            "Post this? It gets Instagram's next free Posting time"
            + (" and the video TikTok's" if tiktok else "")
            + "; you can pull it back until then."
        )
        if not await confirm(question, "Post"):
            return
        try:
            done = await api.post_suggestion(token(), self._id, tiktok)
        except api.ApiError as problem:
            self.error.show(problem.message)
            return
        message = f"Scheduled for {shown(done['scheduled_for'])}."
        if done["tiktok"]:
            message += f" On TikTok: {shown(done['tiktok']['scheduled_for'])}."
        ui.notify(message)
        await self.reload()

    async def _pull_back(self) -> None:
        try:
            await api.pull_back_suggestion(token(), self._id)
        except api.ApiError as problem:
            self.error.show(problem.message)
            return
        ui.notify("The post was pulled back to Review.")
        await self.reload()

    def _editor(self) -> None:
        suggestion = self.suggestion
        media = suggestion["ranking"]
        _numbered(media)
        chosen = suggestion["chosen"]["id"] if suggestion["chosen"] else None
        medium = (
            ui.select(
                _medium_options(suggestion),
                value=chosen,
                label="Photo or video to post (best first)",
            )
            .classes("w-full")
            .mark("suggestion-medium")
        )
        title = (
            ui.input("Title (at most 80 characters)", value=suggestion["title"] or "")
            .props("counter maxlength=80")
            .classes("w-full")
            .mark("suggestion-title")
        )
        caption = (
            ui.textarea("Caption", value=suggestion["caption"] or "")
            .props("autogrow counter")
            .classes("w-full")
            .mark("suggestion-caption")
        )

        async def save() -> None:
            if medium.value is None:
                self.error.show("Choose the photo or video to post.")
                return
            try:
                await api.edit_suggestion(
                    token(),
                    self._id,
                    {
                        "title": title.value or "",
                        "caption": caption.value or "",
                        "chosen_medium_id": medium.value,
                    },
                )
            except api.ApiError as problem:
                self.error.show(problem.message)
                return
            ui.notify("The suggestion was saved.")
            await self.reload()

        self._reviewed()
        if (
            suggestion["state"] == "waiting"
            and suggestion["has_video"]
            and not suggestion["tiktok"]
            and self.creator is not None
        ):
            self._tiktok_choices()
        with ui.row().classes("items-center gap-2"):
            save_button = SaveButton([medium, title, caption], save)
            save_button.button.mark("save-suggestion")
            if suggestion["state"] == "waiting":
                # What is posted is what is saved: save changes first.
                ui.button("Post", icon="send", on_click=self._post).bind_enabled_from(
                    save_button.button, "enabled", backward=lambda unsaved: not unsaved
                ).mark("post-suggestion")
            ui.button("Refuse", on_click=self._refuse).props("outline color=dark").mark(
                "refuse-suggestion"
            )
            self._generate_button()

    def _generate_button(self) -> None:
        ui.button("Generate again", icon="auto_awesome", on_click=self._generate).props(
            "flat color=dark"
        ).mark("generate-again")

    async def _refuse(self) -> None:
        with ui.dialog() as dialog, ui.card().classes("w-full max-w-md"):
            ui.label(
                "Refuse this suggestion? There will be no post for "
                f"{self.suggestion['project']['title']} this week."
            )
            reason = ui.input("Reason for the team (optional)").classes("w-full")
            reason.mark("refusal-reason")
            with ui.row():
                ui.button("Refuse", on_click=lambda: dialog.submit(True)).mark(
                    "confirm-refusal"
                )
                ui.button("Cancel", on_click=lambda: dialog.submit(False)).props(
                    "flat color=dark"
                )
        sure = await dialog
        dialog.delete()
        if not sure:
            return
        try:
            await api.refuse_suggestion(token(), self._id, reason.value or None)
        except api.ApiError as problem:
            self.error.show(problem.message)
            return
        ui.notify("The suggestion was refused.")
        await self.reload()

    async def _generate(self) -> None:
        question = "Let the AI write this suggestion again? Your changes are lost."
        if not await confirm(question, "Generate again"):
            return
        try:
            await api.generate_suggestion(token(), self._id)
        except api.ApiError as problem:
            self.error.show(problem.message)
            return
        await self.reload()


def register() -> None:
    @role_page("/post-suggestions", "Post suggestions", {"superuser", "teacher"})
    async def suggestions_page(user: api.CurrentUser) -> None:
        @ui.refreshable
        async def slideshow() -> None:
            found = await api.latest_slideshow(token())
            if found is not None:
                SlideshowCard(found, slideshow.refresh)
            slideshow_checker.active = bool(found) and found["state"] == "generating"

        slideshow_checker = ui.timer(
            GENERATING_SECONDS, lambda: slideshow.refresh(), active=False
        )
        await slideshow()

        @ui.refreshable
        async def found_list() -> None:
            found = await api.post_suggestions(token(), mine=bool(only_mine.value))
            if not found:
                ui.label("No Post suggestions yet.")
            creator = None
            if any(s["has_video"] and s["state"] == "waiting" for s in found):
                creator = await api.tiktok_creator_info(token())
            for suggestion in found:
                SuggestionCard(suggestion, found_list.refresh, creator)
            # Look again while the AI is writing one.
            checker.active = any(s["state"] == "generating" for s in found)

        ui.label(
            "The AI writes a suggestion at 07:00 on the Upload deadline's weekday, "
            "a week after each Upload week, for every Active Project with photos "
            "or a video."
        ).classes("text-caption")
        # A Teacher sees their own Projects first; the Superuser owns none.
        only_mine = ui.switch(
            "Only my Projects",
            value=user.role == "teacher",
            on_change=lambda: found_list.refresh(),
        ).mark("only-mine")
        checker = ui.timer(GENERATING_SECONDS, found_list.refresh, active=False)
        await found_list()
