"""Post suggestions and their Review (spec #110, #115): Teachers and the
Superuser edit the AI's suggestion, pick another photo or the video, refuse it,
let the AI start over, or write the post themselves when the AI couldn't."""

from typing import Any

from nicegui import ui

from pmp_frontend import api
from pmp_frontend.shell import ErrorMessage, SaveButton, confirm, role_page, token
from pmp_frontend.social_page import media_grid
from pmp_frontend.times import shown

STATES = {
    "generating": ("Being written", "grey-7"),
    "waiting": ("Waiting for Review", "primary"),
    "failed": ("No suggestion", "grey-7"),
    "refused": ("Refused", "grey-7"),
}
# How often the page looks again while the AI is writing.
GENERATING_SECONDS = 5.0


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

    def __init__(self, suggestion: dict[str, Any], reload) -> None:
        self.suggestion = suggestion
        self.reload = reload
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

    def _other(self) -> None:
        self._reviewed()

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
        with ui.row().classes("items-center gap-2"):
            SaveButton([medium, title, caption], save).button.mark("save-suggestion")
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
        async def found_list() -> None:
            found = await api.post_suggestions(token(), mine=bool(only_mine.value))
            if not found:
                ui.label("No Post suggestions yet.")
            for suggestion in found:
                SuggestionCard(suggestion, found_list.refresh)
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
