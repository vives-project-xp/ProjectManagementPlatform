"""Also on TikTok (spec #145, #147): a Posted suggestion's video also goes on
TikTok, with its own line, Posting times (Monday-Friday 17:00 by default) and
state next to the Instagram post. At its Posting time it is published with
Direct Post; a failure is tried again once 10 minutes later, then it moves to
To post today, as do all TikTok posts while the account isn't connected."""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from pmp_backend.models import PostSuggestion, TikTokPost, User, WeeklyMedium
from pmp_backend.services import posting, social, tiktok_connection
from pmp_backend.services.instagram import ChannelError
from pmp_backend.services.suggestions import (
    ReviewConflictError,
    ReviewError,
    ReviewNotFoundError,
)
from pmp_backend.services.tiktok import PRIVACY_LEVELS, TikTok, VideoPost
from pmp_backend.settings import Settings

log = logging.getLogger(__name__)

RETRY_AFTER = timedelta(minutes=10)
MAX_ATTEMPTS = 2
# TikTok's limit for a video's caption.
MAX_CAPTION = 2200
RECENTLY_PUBLISHED = 10
NOT_CONNECTED = (
    "TikTok isn't connected (Social media screen), so this video is posted by hand."
)


@dataclass(frozen=True)
class Choice:
    """The reviewer's choices for the TikTok video."""

    privacy_level: str
    allow_comment: bool = True
    allow_duet: bool = False
    allow_stitch: bool = False


def video_of(suggestion: PostSuggestion) -> WeeklyMedium | None:
    """The Weekly update's video once it is ready, the one TikTok posts."""
    return next(
        (
            medium
            for medium in suggestion.weekly_update.media
            if medium.kind == "video" and medium.state == "ready"
        ),
        None,
    )


def _now(session: Session) -> datetime:
    return session.scalar(select(func.now()))


def _project_of(post: TikTokPost) -> int:
    return post.suggestion.weekly_update.project_id


def add(session: Session, suggestion: PostSuggestion, choice: Choice) -> None:
    """Put the suggestion's video in TikTok's line (when Posting it with Also
    on TikTok ticked); kept as it is when it already has a TikTok post."""
    if choice.privacy_level not in PRIVACY_LEVELS:
        raise ReviewError("Choose who can see the video on TikTok.")
    medium = video_of(suggestion)
    if medium is None:
        raise ReviewConflictError("This Weekly update has no video for TikTok.")
    if suggestion.tiktok_post is not None:
        return
    session.add(
        TikTokPost(
            suggestion_id=suggestion.id,
            medium_id=medium.id,
            state="scheduled",
            privacy_level=choice.privacy_level,
            allow_comment=choice.allow_comment,
            allow_duet=choice.allow_duet,
            allow_stitch=choice.allow_stitch,
            queued_at=_now(session),
        )
    )
    session.flush()


def plan(session: Session) -> None:
    """Give every Scheduled TikTok post a Posting time again, like Instagram's
    line: first free times, in the order they were Posted, never the same
    Project twice in a row; posts due within the margin keep their time."""
    now = _now(session)
    scheduled = session.scalars(
        select(TikTokPost)
        .where(TikTokPost.state == "scheduled")
        .order_by(TikTokPost.queued_at, TikTokPost.id)
        .with_for_update(of=TikTokPost)
    ).all()
    fixed = [
        p
        for p in scheduled
        if p.scheduled_for and p.scheduled_for <= now + posting.MARGIN
    ]
    line = [p for p in scheduled if p not in fixed]
    taken = {p.scheduled_for for p in fixed}
    before = session.scalar(
        select(TikTokPost)
        .where(TikTokPost.scheduled_for.is_not(None), TikTokPost.state != "scheduled")
        .order_by(TikTokPost.scheduled_for.desc())
        .limit(1)
    )
    previous = (
        _project_of(fixed[-1]) if fixed else (_project_of(before) if before else None)
    )
    settings = social.get_settings(session)
    times = (
        moment
        for moment in posting.posting_times(
            settings.tiktok_weekdays, settings.tiktok_times, now + posting.MARGIN
        )
        if moment not in taken
    )
    while line:
        pick = next((p for p in line if _project_of(p) != previous), line[0])
        line.remove(pick)
        pick.scheduled_for = next(times, None)
        previous = _project_of(pick)
    session.flush()


def _locked(session: Session, suggestion_id: int, states: set[str]) -> TikTokPost:
    post = session.scalar(
        select(TikTokPost)
        .where(TikTokPost.suggestion_id == suggestion_id)
        .with_for_update(of=TikTokPost)
        .execution_options(populate_existing=True)
    )
    if post is None:
        raise ReviewNotFoundError("This suggestion has no TikTok post (any more).")
    if post.state not in states:
        raise ReviewConflictError(
            "This TikTok post changed meanwhile. Reload the page and try again."
        )
    return post


def pull_back(session: Session, suggestion_id: int) -> None:
    """Take the video out of TikTok's line; the Instagram post stays."""
    post = _locked(session, suggestion_id, {"scheduled"})
    session.delete(post)
    session.flush()
    plan(session)
    session.commit()


def mark_posted(session: Session, user: User, suggestion_id: int) -> None:
    """Someone posted the video on TikTok by hand; it is kept as posted."""
    post = _locked(session, suggestion_id, {"to_post_by_hand"})
    post.state = "posted_by_hand"
    post.posted_by_id = user.id
    post.posted_at = _now(session)
    medium = session.get(WeeklyMedium, post.medium_id or 0)
    if medium is not None:
        medium.posted = True
    session.commit()


def caption_of(suggestion: PostSuggestion) -> str:
    """Like Instagram's: the title as the first line."""
    return f"{suggestion.title}\n\n{suggestion.caption}"[:MAX_CAPTION]


def _to_post_by_hand(post: TikTokPost, reason: str) -> None:
    post.state = "to_post_by_hand"
    post.error = reason[:500]
    post.retry_at = None


def publish_due(
    session: Session, client: TikTok, settings: Settings, now: datetime
) -> list[int]:
    """Publish every Scheduled TikTok post whose Posting time (or retry) has
    come; the suggestion ids of those published."""
    token = tiktok_connection.access_token(session, settings, now)
    session.commit()
    due = list(
        session.scalars(
            select(TikTokPost.id)
            .where(
                TikTokPost.state == "scheduled",
                TikTokPost.scheduled_for <= now,
                TikTokPost.retry_at.is_(None) | (TikTokPost.retry_at <= now),
            )
            .order_by(TikTokPost.scheduled_for)
        )
    )
    published = []
    for post_id in due:
        # Locked while publishing: Pull back waits, then finds it published.
        post = session.scalars(
            select(TikTokPost)
            .where(TikTokPost.id == post_id, TikTokPost.state == "scheduled")
            .with_for_update(of=TikTokPost, skip_locked=True)
        ).first()
        if post is None:
            session.rollback()
            continue
        medium = session.get(WeeklyMedium, post.medium_id or 0)
        if token is None:
            _to_post_by_hand(post, NOT_CONNECTED)
        elif medium is None:
            _to_post_by_hand(post, "The video doesn't exist any more.")
        else:
            try:
                url = _post_video(client, settings, token, post, medium)
            except _NotAllowedError as error:
                _to_post_by_hand(post, str(error))
            except ChannelError as error:
                log.warning("Publishing TikTok post %s failed: %s", post_id, error)
                post.attempts += 1
                if post.attempts >= MAX_ATTEMPTS:
                    _to_post_by_hand(post, f"Publishing on TikTok failed: {error}")
                else:
                    post.error = str(error)[:500]
                    post.retry_at = now + RETRY_AFTER
            else:
                post.state = "published"
                post.posted_at = now
                post.published_url = url[:500] or None
                post.error = post.retry_at = None
                medium.posted = True
                published.append(post.suggestion_id)
        session.commit()
    return published


class _NotAllowedError(Exception):
    """TikTok no longer allows the reviewer's choice for this account."""


def _post_video(
    client: TikTok,
    settings: Settings,
    token: str,
    post: TikTokPost,
    medium: WeeklyMedium,
) -> str:
    # TikTok asks apps to look at the creator info right before posting.
    info = client.creator_info(token)
    if post.privacy_level not in info.privacy_levels:
        shown = PRIVACY_LEVELS.get(post.privacy_level, post.privacy_level)
        raise _NotAllowedError(
            f'TikTok doesn\'t allow "{shown}" for this account right now.'
        )
    video = social.medium_path(
        settings.social_media_dir, post.suggestion.weekly_update.project_id, medium
    )
    return client.publish_video(
        token,
        video,
        VideoPost(
            caption=caption_of(post.suggestion),
            privacy_level=post.privacy_level,
            allow_comment=post.allow_comment and not info.comment_disabled,
            allow_duet=post.allow_duet and not info.duet_disabled,
            allow_stitch=post.allow_stitch and not info.stitch_disabled,
        ),
    )


def lists(session: Session) -> tuple[list[int], list[int], list[int]]:
    """Suggestion ids of the TikTok posts To post today (oldest first),
    Scheduled (soonest first) and published lately (newest first)."""

    def ids(*where, order) -> list[int]:
        return list(
            session.scalars(
                select(TikTokPost.suggestion_id).where(*where).order_by(order)
            )
        )

    to_post = ids(TikTokPost.state == "to_post_by_hand", order=TikTokPost.scheduled_for)
    scheduled = ids(TikTokPost.state == "scheduled", order=TikTokPost.scheduled_for)
    published = ids(TikTokPost.state == "published", order=TikTokPost.posted_at.desc())[
        :RECENTLY_PUBLISHED
    ]
    return to_post, scheduled, published
