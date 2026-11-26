"""Scheduled posts (spec #110, #116, #117): the posts whose Posting time has
come and that weren't published automatically, to publish by hand (To post
today); Instagram's line of Scheduled posts; and the last posts published."""

from typing import Any

from nicegui import ui

from pmp_frontend import api
from pmp_frontend.review_page import SuggestionCard, tiktok_text
from pmp_frontend.shell import ErrorMessage, confirm, role_page, token
from pmp_frontend.slideshow_card import SlideshowCard
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


def _tiktok_to_post_card(post: dict[str, Any], reload) -> None:
    """A TikTok video whose Posting time has come and that wasn't published
    automatically (#147): download it, copy the caption, post it by hand."""
    tiktok = post["tiktok"]

    async def posted() -> None:
        if not await confirm(f"Did you post {post['title']} on TikTok?", "Posted"):
            return
        try:
            await api.mark_tiktok_posted(token(), post["id"])
        except api.ApiError as problem:
            error.show(problem.message)
            return
        ui.notify("Marked as posted on TikTok.")
        await reload()

    def copy() -> None:
        ui.clipboard.write(post_text(post))
        ui.notify("The caption was copied.")

    with ui.card().classes("w-full max-w-3xl").mark(f"tiktok-to-post-{post['id']}"):
        with ui.row().classes("w-full items-center"):
            ui.label(post["project"]["title"]).classes("text-h6")
            ui.label(f"Posting time {shown(tiktok['scheduled_for'])}").classes(
                "text-caption"
            )
        ui.label(post["title"]).classes("font-medium")
        ui.label(post["caption"]).classes("whitespace-pre-wrap")
        ui.label(
            "Who can see it: "
            + {
                "PUBLIC_TO_EVERYONE": "Everyone",
                "MUTUAL_FOLLOW_FRIENDS": "Friends",
                "FOLLOWER_OF_CREATOR": "Followers",
                "SELF_ONLY": "Only me",
            }.get(tiktok["privacy_level"], tiktok["privacy_level"])
        ).classes("text-caption")
        if tiktok["error"]:
            with ui.row().classes("items-center gap-2 no-wrap").mark("tiktok-error"):
                ui.icon("warning", color="primary")
                ui.label(tiktok["error"])
        error = ErrorMessage()
        with ui.row().classes("items-center gap-2"):
            if tiktok["medium_id"]:
                ui.button(
                    "Download video",
                    icon="download",
                    on_click=lambda: ui.download(
                        medium_url({"id": tiktok["medium_id"]}),
                        f"{post['project']['title']}-{tiktok['medium_id']}.mp4",
                    ),
                ).props("outline color=dark").mark("download-tiktok-video")
            ui.button("Copy caption", icon="content_copy", on_click=copy).props(
                "outline color=dark"
            ).mark("copy-tiktok-caption")
            ui.button("Posted", icon="done", on_click=posted).mark("mark-tiktok-posted")


def _tiktok_scheduled_row(post: dict[str, Any], reload) -> None:
    async def pull_back() -> None:
        try:
            await api.pull_back_tiktok(token(), post["id"])
        except api.ApiError as problem:
            ui.notify(problem.message, type="negative")
            return
        ui.notify("The video was taken off TikTok's line.")
        await reload()

    with ui.row().classes("items-center gap-2").mark(f"tiktok-scheduled-{post['id']}"):
        ui.icon("schedule", color="dark")
        ui.label(f"{post['project']['title']}: {post['title']}").classes("font-medium")
        ui.label(tiktok_text(post["tiktok"])).classes("text-caption")
        ui.button("Pull back", icon="undo", on_click=pull_back).props(
            "flat dense color=dark"
        ).mark(f"tiktok-row-pull-back-{post['id']}")


def _tiktok_lists(found: dict[str, Any], reload) -> None:
    ui.label("TikTok videos").classes("text-h5")
    if not found["tiktok_automatic"]:
        with ui.row().classes("items-center gap-2 no-wrap").mark("tiktok-notice"):
            ui.icon("info", color="dark")
            ui.label(
                found["tiktok_error"]
                or "TikTok isn't connected (Social media screen): publish the videos "
                "yourself, then press Posted."
            )
    ui.label("To post today on TikTok").classes("text-h6")
    if not found["tiktok_to_post"]:
        ui.label("Nothing to post on TikTok right now.").mark("nothing-on-tiktok")
    for post in found["tiktok_to_post"]:
        _tiktok_to_post_card(post, reload)
    ui.label("Scheduled on TikTok").classes("text-h6")
    if not found["tiktok_scheduled"]:
        ui.label("No TikTok videos scheduled.")
    for post in found["tiktok_scheduled"]:
        _tiktok_scheduled_row(post, reload)
    if found["tiktok_published"]:
        ui.label("Published on TikTok").classes("text-h6")
        for post in found["tiktok_published"]:
            with (
                ui.row()
                .classes("items-center gap-2")
                .mark(f"tiktok-published-{post['id']}")
            ):
                ui.icon("check_circle", color="dark")
                ui.label(f"{post['project']['title']}: {post['title']}").classes(
                    "font-medium"
                )
                ui.label(shown(post["tiktok"]["posted_at"])).classes("text-caption")
                if post["tiktok"]["published_url"]:
                    ui.link(
                        "View on TikTok", post["tiktok"]["published_url"], new_tab=True
                    )


async def _slideshow_lists(reload) -> None:
    """The Weekly slideshow (#150): to finish (in the TikTok app, or by hand),
    Scheduled, and lately posted."""
    found = await api.slideshow_lists(token())
    ui.label("Weekly slideshow").classes("text-h5")
    ui.label("To post today: Weekly slideshow").classes("text-h6")
    if not found["to_finish"]:
        ui.label("No slideshow to post right now.").mark("no-slideshow-to-post")
    for slideshow in found["to_finish"]:
        SlideshowCard(slideshow, reload)
    if found["scheduled"]:
        ui.label("Scheduled: Weekly slideshow").classes("text-h6")
        for slideshow in found["scheduled"]:
            SlideshowCard(slideshow, reload)
    if found["posted"]:
        ui.label("Posted: Weekly slideshow").classes("text-h6")
        for slideshow in found["posted"]:
            with (
                ui.row()
                .classes("items-center gap-2")
                .mark(f"slideshow-posted-{slideshow['id']}")
            ):
                ui.icon("check_circle", color="dark")
                ui.label(slideshow["title"] or "").classes("font-medium")
                ui.label(shown(slideshow["posted_at"])).classes("text-caption")


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
            _tiktok_lists(found, lists.refresh)
            await _slideshow_lists(lists.refresh)

        await lists()
