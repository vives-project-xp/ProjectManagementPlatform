"""Scheduled posts (spec #110, #116, #117): the posts whose Posting time has
come and that weren't published automatically, to publish by hand (To post
today); Instagram's line of Scheduled posts; and the last posts published."""

from typing import Any

from nicegui import ui

from pmp_frontend import api
from pmp_frontend.review_page import SuggestionCard
from pmp_frontend.shell import ErrorMessage, confirm, role_page, token
from pmp_frontend.social_page import media_grid, medium_url
from pmp_frontend.times import shown


def post_text(post: dict[str, Any]) -> str:
    """What to paste on Instagram: the title as the caption's first line."""
    return f"{post['title']}\n\n{post['caption']}"


def _download_name(post: dict[str, Any]) -> str:
    medium = post["chosen"]
    extension = "jpg" if medium["kind"] == "photo" else "mp4"
    return f"{post['project']['title']}-{medium['id']}.{extension}"


def _to_post_card(post: dict[str, Any], reload) -> None:
    async def posted() -> None:
        if not await confirm(f"Did you post {post['title']}?", "Posted"):
            return
        try:
            await api.mark_posted(token(), post["id"])
        except api.ApiError as problem:
            error.show(problem.message)
            return
        ui.notify("Marked as posted.")
        await reload()

    def copy() -> None:
        ui.clipboard.write(post_text(post))
        ui.notify("The caption was copied.")

    with ui.card().classes("w-full max-w-3xl").mark(f"to-post-{post['id']}"):
        with ui.row().classes("w-full items-center"):
            ui.label(post["project"]["title"]).classes("text-h6")
            ui.label(f"Posting time {shown(post['scheduled_for'])}").classes(
                "text-caption"
            )
        with ui.row().classes("w-full gap-4 items-start no-wrap"):
            if post["chosen"]:
                media_grid([post["chosen"]])
            with ui.column().classes("gap-1 min-w-0"):
                ui.label(post["title"]).classes("font-medium")
                ui.label(post["caption"]).classes("whitespace-pre-wrap")
        if post["publish_error"]:
            # Why automatic publishing didn't do it (#117).
            with ui.row().classes("items-center gap-2 no-wrap").mark("publish-error"):
                ui.icon("warning", color="primary")
                ui.label(post["publish_error"])
        error = ErrorMessage()
        with ui.row().classes("items-center gap-2"):
            if post["chosen"]:
                ui.button(
                    "Download media",
                    icon="download",
                    on_click=lambda: ui.download(
                        medium_url(post["chosen"]), _download_name(post)
                    ),
                ).props("outline color=dark").mark("download-media")
            ui.button("Copy caption", icon="content_copy", on_click=copy).props(
                "outline color=dark"
            ).mark("copy-caption")
            ui.button("Posted", icon="done", on_click=posted).mark("mark-posted")


def channel_notice(channel: dict[str, Any]) -> str | None:
    """What staff should know about automatic publishing, if anything."""
    if not channel["automatic"]:
        return (
            "Automatic publishing on Instagram isn't set up: publish the posts "
            "yourself: download the photo or video, copy the caption, then press "
            "Posted."
        )
    if channel["refresh_error"]:
        until = (
            f" It stops working on {shown(channel['expires_at'])}."
            if channel["expires_at"]
            else ""
        )
        return (
            f"Instagram's token couldn't be refreshed: {channel['refresh_error']}."
            f"{until}"
        )
    if not channel["photos_automatic"]:
        return (
            "Reels are published automatically; photo posts come here until the "
            "site is reachable from the internet."
        )
    return None


def _published_row(post: dict[str, Any]) -> None:
    with ui.row().classes("items-center gap-2").mark(f"published-{post['id']}"):
        ui.icon("check_circle", color="dark")
        ui.label(f"{post['project']['title']}: {post['title']}").classes("font-medium")
        ui.label(shown(post["posted_at"])).classes("text-caption")
        if post["published_url"]:
            ui.link("View on Instagram", post["published_url"], new_tab=True).mark(
                "instagram-link"
            )


def register() -> None:
    @role_page("/scheduled-posts", "Scheduled posts", {"superuser", "teacher"})
    async def scheduled_page(user: api.CurrentUser) -> None:
        @ui.refreshable
        async def lists() -> None:
            found = await api.scheduled_posts(token())
            notice = channel_notice(found["channel"])
            if notice:
                with (
                    ui.row()
                    .classes("items-center gap-2 no-wrap")
                    .mark("channel-notice")
                ):
                    ui.icon("info", color="dark")
                    ui.label(notice)
            ui.label("To post today").classes("text-h6")
            ui.label(
                "Posts whose Posting time has come that weren't published "
                "automatically: download the photo or video, copy the caption, "
                "post it on Instagram, then press Posted."
            ).classes("text-caption")
            if not found["to_post"]:
                ui.label("Nothing to post right now.").mark("nothing-to-post")
            for post in found["to_post"]:
                _to_post_card(post, lists.refresh)
            ui.label("Scheduled").classes("text-h6")
            if not found["scheduled"]:
                ui.label("No Scheduled posts.")
            for post in found["scheduled"]:
                SuggestionCard(post, lists.refresh)
            if found["published"]:
                ui.label("Published").classes("text-h6")
                for post in found["published"]:
                    _published_row(post)

        await lists()
