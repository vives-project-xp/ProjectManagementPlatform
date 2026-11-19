"""Automatic publishing of Scheduled posts on Instagram (spec #110, #117).

At its Posting time a Scheduled post is published on the Channel: a photo as a
photo post through a short-lived Publish link (ADR 0010), the video as a Reel.
A failure is tried again once, 10 minutes later; then the post moves to To
post today with the reason. Without a token (or, for a photo, without
PUBLIC_MEDIA_URL) the post goes to To post today at once, as before.

The Channel's long-lived token lives in the database (first taken from
INSTAGRAM_TOKEN) and is refreshed a week before it expires."""

import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from pmp_backend.errors import NotFound
from pmp_backend.models import ChannelToken, PostSuggestion, PublishLink, WeeklyMedium
from pmp_backend.services import instagram, social
from pmp_backend.services.instagram import Channel, ChannelError
from pmp_backend.settings import Settings

log = logging.getLogger(__name__)

CHANNEL = "instagram"
LINK_LIFETIME = timedelta(hours=1)
# 24 random bytes: 192 bits, 32 characters.
CODE_BYTES = 24
RETRY_AFTER = timedelta(minutes=10)
# Tries per post before it goes to To post today.
MAX_ATTEMPTS = 2
REFRESH_BEFORE = timedelta(days=7)
# A failed refresh is tried again a day later, not every round.
REFRESH_RETRY = timedelta(days=1)
NO_LINK = "This link doesn't exist (any more)."


class NotAutomaticError(Exception):
    """This post can't be published automatically; the text says why."""


# The token


def channel_token(session: Session, settings: Settings) -> ChannelToken | None:
    """The Channel's token, taken from INSTAGRAM_TOKEN the first time; None
    without INSTAGRAM_TOKEN (publishing is then off, even with a stored one)."""
    if not instagram.is_configured(settings):
        return None
    row = session.get(ChannelToken, CHANNEL)
    if row is None:
        row = ChannelToken(
            channel=CHANNEL, token=settings.instagram_token.get_secret_value()
        )
        session.add(row)
        session.flush()
    return row


def refresh_token(
    session: Session, channel: Channel, settings: Settings, now: datetime
) -> bool:
    """Refresh the token when it expires within a week (or its expiry is still
    unknown); a failure is kept for the notice. Whether it was refreshed. A
    token that never expires (INSTAGRAM_REFRESH_URL empty) is left alone."""
    row = channel_token(session, settings)
    if row is None or not settings.instagram_refresh_url:
        session.commit()
        return False
    if row.expires_at is not None and row.expires_at - now > REFRESH_BEFORE:
        session.commit()
        return False
    if row.refreshed_at is not None and now - row.refreshed_at < REFRESH_RETRY:
        session.commit()
        return False
    row.refreshed_at = now
    try:
        new = channel.refresh(row.token, now)
    except ChannelError as error:
        row.refresh_error = str(error)[:500]
        session.commit()
        log.warning("Refreshing the Instagram token failed: %s", error)
        return False
    row.token, row.expires_at, row.refresh_error = new.token, new.expires_at, None
    session.commit()
    return True


@dataclass(frozen=True)
class ChannelStatus:
    """What staff see about automatic publishing (never the token)."""

    automatic: bool
    photos_automatic: bool
    expires_at: datetime | None
    refresh_error: str | None


def status(session: Session, settings: Settings) -> ChannelStatus:
    row = channel_token(session, settings)
    session.commit()
    return ChannelStatus(
        automatic=row is not None,
        photos_automatic=row is not None and bool(settings.public_media_url),
        expires_at=row.expires_at if row else None,
        refresh_error=row.refresh_error if row else None,
    )


# Publish links


def _code() -> str:
    return secrets.token_urlsafe(CODE_BYTES)


def create_link(
    session: Session, suggestion: PostSuggestion, medium: WeeklyMedium, now: datetime
) -> PublishLink:
    link = PublishLink(
        code=_code(),
        suggestion_id=suggestion.id,
        medium_id=medium.id,
        expires_at=now + LINK_LIFETIME,
    )
    session.add(link)
    return link


def link_url(settings: Settings, link: PublishLink) -> str:
    return f"{settings.public_media_url.rstrip('/')}/social/{link.code}"


def linked_medium(
    session: Session, media_dir: Path, code: str, now: datetime
) -> tuple[WeeklyMedium, Path]:
    """The Medium behind a valid Publish link; NotFound when the code is
    unknown, expired, or its post was published or taken out of the line."""
    link = session.get(PublishLink, code)
    if link is None or link.expires_at <= now:
        raise NotFound(NO_LINK)
    suggestion = session.get(PostSuggestion, link.suggestion_id)
    medium = session.get(WeeklyMedium, link.medium_id)
    if suggestion is None or suggestion.state != "scheduled" or medium is None:
        raise NotFound(NO_LINK)
    path = social.medium_path(media_dir, suggestion.weekly_update.project_id, medium)
    if not path.is_file():
        raise NotFound(NO_LINK)
    return medium, path


# Publishing


def _due(session: Session, now: datetime) -> list[int]:
    return list(
        session.scalars(
            select(PostSuggestion.id)
            .where(
                PostSuggestion.state == "scheduled",
                PostSuggestion.scheduled_for <= now,
                (PostSuggestion.publish_retry_at.is_(None))
                | (PostSuggestion.publish_retry_at <= now),
            )
            .order_by(PostSuggestion.scheduled_for)
        )
    )


def _text(suggestion: PostSuggestion) -> str:
    # Like Copy caption on To post today: the title as the first line.
    return f"{suggestion.title}\n\n{suggestion.caption}"


def _prepare_links(
    session: Session, settings: Settings, ids: list[int], now: datetime
) -> dict[int, PublishLink]:
    """A fresh Publish link for every due photo post, committed before
    Instagram is asked to download it."""
    links: dict[int, PublishLink] = {}
    if not settings.public_media_url:
        return links
    for suggestion_id in ids:
        suggestion = session.get(PostSuggestion, suggestion_id)
        medium = session.get(WeeklyMedium, suggestion.chosen_medium_id or 0)
        if medium is not None and medium.kind == "photo":
            links[suggestion_id] = create_link(session, suggestion, medium, now)
    session.commit()
    return links


def _publish(
    channel: Channel,
    settings: Settings,
    token: str,
    suggestion: PostSuggestion,
    medium: WeeklyMedium | None,
    link: PublishLink | None,
) -> instagram.Published:
    if medium is None:
        raise NotAutomaticError("The chosen photo or video doesn't exist any more.")
    if medium.kind == "photo":
        if link is None:
            raise NotAutomaticError(
                "Photo posts are published automatically only once the site is "
                "reachable from the internet."
            )
        return channel.publish_photo(token, link_url(settings, link), _text(suggestion))
    video = social.medium_path(
        settings.social_media_dir, suggestion.weekly_update.project_id, medium
    )
    return channel.publish_reel(token, video, _text(suggestion))


def _to_post_by_hand(suggestion: PostSuggestion, reason: str) -> None:
    suggestion.state = "to_post_by_hand"
    suggestion.publish_error = reason[:500]
    suggestion.publish_retry_at = None


def publish_due(
    session: Session, channel: Channel, settings: Settings, now: datetime
) -> list[int]:
    """Publish every Scheduled post whose Posting time (or retry) has come; the
    ids of those published."""
    row = channel_token(session, settings)
    token = row.token if row else None
    session.commit()
    ids = _due(session, now)
    links = _prepare_links(session, settings, ids, now) if token else {}
    published = []
    for suggestion_id in ids:
        # Locked while publishing: Pull back waits, then finds it published.
        suggestion = session.scalars(
            select(PostSuggestion)
            .where(
                PostSuggestion.id == suggestion_id,
                PostSuggestion.state == "scheduled",
            )
            .with_for_update(of=PostSuggestion, skip_locked=True)
        ).first()
        if suggestion is None:
            # Pulled back (or busy elsewhere) in the meantime.
            session.rollback()
            continue
        medium = session.get(WeeklyMedium, suggestion.chosen_medium_id or 0)
        if token is None:
            suggestion.state = "to_post_by_hand"
            session.commit()
            continue
        try:
            done = _publish(
                channel, settings, token, suggestion, medium, links.get(suggestion_id)
            )
        except NotAutomaticError as error:
            _to_post_by_hand(suggestion, str(error))
        except ChannelError as error:
            log.warning("Publishing post %s failed: %s", suggestion_id, error)
            suggestion.publish_attempts += 1
            if suggestion.publish_attempts >= MAX_ATTEMPTS:
                _to_post_by_hand(suggestion, f"Publishing on Instagram failed: {error}")
            else:
                suggestion.publish_error = str(error)[:500]
                suggestion.publish_retry_at = now + RETRY_AFTER
        else:
            suggestion.state = "published"
            suggestion.posted_at = now
            suggestion.published_url = done.url[:500] or None
            suggestion.publish_error = suggestion.publish_retry_at = None
            medium.posted = True
            # Its links stop working at once.
            session.execute(
                delete(PublishLink).where(PublishLink.suggestion_id == suggestion.id)
            )
            published.append(suggestion.id)
        session.commit()
    return published
