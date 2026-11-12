"""Post suggestions (spec #110): made by the AI at 07:00 on the Upload
deadline's weekday, a week after an Upload week closed, for every Active Project
with a Weekly update and at least one usable photo or video."""

import asyncio
import io
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from pmp_backend.domain import ProjectStatus
from pmp_backend.errors import Conflict, NotFound, Refused
from pmp_backend.models import (
    PostSuggestion,
    Project,
    User,
    WeeklyMedium,
    WeeklyUpdate,
)
from pmp_backend.services import post_ai, social
from pmp_backend.services.post_ai import LLM, AiError

log = logging.getLogger(__name__)

BRUSSELS = ZoneInfo("Europe/Brussels")
GENERATE_AT = time(7, 0)
MAX_ATTEMPTS = 3
# 3 tries within an hour (Q18).
RETRY_AFTER = timedelta(minutes=20)
# The photos the AI sees: 3 of 1600 px stay well under its 8.8 megapixels.
AI_LONG_SIDE = 1600
EVERY_SECONDS = 60


def generate_at(closes_at: datetime) -> datetime:
    """07:00 Belgian time on the same weekday, a week after the week closed."""
    day = closes_at.astimezone(BRUSSELS).date() + timedelta(days=7)
    return datetime.combine(day, GENERATE_AT, BRUSSELS)


def _usable(update: WeeklyUpdate) -> list[WeeklyMedium]:
    """Photos by quality score (best first), then the video, once ready."""
    ready = [medium for medium in update.media if medium.state == "ready"]
    photos = sorted(
        (m for m in ready if m.kind == "photo"),
        key=lambda m: m.quality_score or 0,
        reverse=True,
    )
    return photos + [m for m in ready if m.kind == "video"]


def _label(medium: WeeklyMedium) -> str:
    return f"{medium.kind}-{medium.id}"


def start_due(session: Session, now: datetime) -> list[int]:
    """Start a suggestion for every Weekly update whose moment has come."""
    candidates = session.scalars(
        select(WeeklyUpdate)
        .join(Project, Project.id == WeeklyUpdate.project_id)
        .outerjoin(PostSuggestion, PostSuggestion.weekly_update_id == WeeklyUpdate.id)
        .where(
            Project.status == ProjectStatus.ACTIVE.value,
            PostSuggestion.id.is_(None),
            WeeklyUpdate.closes_at <= now - timedelta(days=6),
        )
    ).all()
    started = []
    for update in candidates:
        if generate_at(update.closes_at) <= now and _usable(update):
            suggestion = PostSuggestion(weekly_update_id=update.id, ranking=[])
            session.add(suggestion)
            session.flush()
            started.append(suggestion.id)
    session.commit()
    return started


def _photo_for_ai(path: Path) -> bytes:
    image = Image.open(path)
    image.thumbnail((AI_LONG_SIDE, AI_LONG_SIDE))
    out = io.BytesIO()
    image.save(out, "JPEG", quality=85)
    return out.getvalue()


def ai_request(
    session: Session, media_dir: Path, update: WeeklyUpdate
) -> tuple[post_ai.AiRequest, list[WeeklyMedium]]:
    """The fixed inputs for the AI (ADR 0009): the Project's title, the update's
    text, the Fixed hashtags, the 3 best photos and the video's AI copy."""
    usable = _usable(update)
    photos = [m for m in usable if m.kind == "photo"][: post_ai.MAX_PHOTOS]
    videos = [m for m in usable if m.kind == "video"]
    project = session.get(Project, update.project_id)
    media = [
        post_ai.Medium(
            _label(m),
            "photo",
            _photo_for_ai(social.medium_path(media_dir, project.id, m)),
        )
        for m in photos
    ] + [
        post_ai.Medium(
            _label(m),
            "video",
            social.medium_path(media_dir, project.id, m, "ai").read_bytes(),
        )
        for m in videos
    ]
    hashtags = social.get_settings(session).fixed_hashtags
    return post_ai.request(project.title, update.text, hashtags, media), usable


def attempt(
    session: Session, llm: LLM, media_dir: Path, suggestion_id: int, now: datetime
) -> None:
    """One try of the AI for a suggestion that is still being made."""
    suggestion = session.get(PostSuggestion, suggestion_id)
    if suggestion is None or suggestion.state != "generating":
        return
    update = suggestion.weekly_update
    hashtags = social.get_settings(session).fixed_hashtags
    try:
        request, usable = ai_request(session, media_dir, update)
        if not request.media:
            raise AiError("This week has no photo or video left.")
        found = post_ai.check(llm.ask(request), request, hashtags)
    except AiError as error:
        suggestion.attempts += 1
        suggestion.last_error = str(error)[:500]
        if suggestion.attempts >= MAX_ATTEMPTS:
            suggestion.state, suggestion.next_attempt_at = "failed", None
        else:
            suggestion.next_attempt_at = now + RETRY_AFTER
        session.commit()
        return
    by_label = {_label(m): m.id for m in usable}
    ranked = [by_label[label] for label in found.ranking]
    # The media the AI didn't see (photos beyond the best 3) come last.
    ranked += [m.id for m in usable if m.id not in ranked]
    suggestion.state = "waiting"
    suggestion.title = found.title
    suggestion.caption = found.caption
    suggestion.chosen_medium_id = by_label[found.chosen]
    suggestion.ranking = ranked
    suggestion.why = found.why
    suggestion.last_error = None
    suggestion.next_attempt_at = None
    session.commit()


def run_once(session: Session, llm: LLM, media_dir: Path, now: datetime) -> None:
    """Start what is due and try every suggestion whose turn it is."""
    start_due(session, now)
    waiting = session.scalars(
        select(PostSuggestion.id).where(
            PostSuggestion.state == "generating",
            (PostSuggestion.next_attempt_at.is_(None))
            | (PostSuggestion.next_attempt_at <= now),
        )
    ).all()
    # One at a time: the endpoint is shared with the whole school.
    for suggestion_id in waiting:
        attempt(session, llm, media_dir, suggestion_id, now)


async def run_forever(
    make_session: Callable[[], Session], llm: LLM, media_dir: Path
) -> None:
    def run() -> None:
        with make_session() as session:
            run_once(session, llm, media_dir, datetime.now(BRUSSELS))

    while True:
        try:
            await asyncio.to_thread(run)
        except Exception:
            # A failing round is logged; the next one tries again.
            log.exception("Making Post suggestions failed")
        await asyncio.sleep(EVERY_SECONDS)


# What staff see


@dataclass(frozen=True)
class SuggestionView:
    suggestion: PostSuggestion
    project: Project
    closes_at: datetime
    media: dict[int, social.MediumView]


def suggestions(session: Session, owner_id: int | None = None) -> list[SuggestionView]:
    """Every Post suggestion (only of Projects `owner_id` is the Product Owner of,
    when given), newest Upload week first."""
    query = (
        select(PostSuggestion)
        .join(WeeklyUpdate, WeeklyUpdate.id == PostSuggestion.weekly_update_id)
        .join(Project, Project.id == WeeklyUpdate.project_id)
        .order_by(WeeklyUpdate.closes_at.desc(), Project.title, PostSuggestion.id)
        .execution_options(populate_existing=True)
    )
    if owner_id is not None:
        query = query.where(Project.product_owner_id == owner_id)
    found = session.scalars(query).all()
    views = []
    for suggestion in found:
        update = suggestion.weekly_update
        week = social.week_view(update, datetime.now(BRUSSELS))
        views.append(
            SuggestionView(
                suggestion=suggestion,
                project=session.get(Project, update.project_id),
                closes_at=update.closes_at,
                media={medium.id: medium for medium in week.media},
            )
        )
    return views


# Review (#115)


class ReviewError(Refused):
    """A Review action was refused; the message is fit to show."""


class ReviewNotFoundError(ReviewError, NotFound):
    pass


class ReviewConflictError(ReviewError, Conflict):
    pass


def locked(session: Session, suggestion_id: int, states: set[str]) -> PostSuggestion:
    suggestion = session.scalar(
        select(PostSuggestion)
        .where(PostSuggestion.id == suggestion_id)
        .with_for_update(of=PostSuggestion)
        .execution_options(populate_existing=True)
    )
    if suggestion is None:
        raise ReviewNotFoundError("This Post suggestion doesn't exist (any more).")
    if suggestion.state not in states:
        raise ReviewConflictError(
            "This suggestion changed meanwhile. Reload the page and try again."
        )
    return suggestion


def mark_reviewed(session: Session, suggestion: PostSuggestion, reviewer: User) -> None:
    suggestion.reviewed_by_id = reviewer.id
    suggestion.reviewed_at = session.scalar(select(func.now()))


def edit(
    session: Session,
    reviewer: User,
    suggestion_id: int,
    *,
    title: str,
    caption: str,
    chosen_medium_id: int,
) -> PostSuggestion:
    """Change the title, caption or medium, on the same rules as the AI's
    answer; writing it yourself turns a failed suggestion into one waiting for
    Review."""
    suggestion = locked(session, suggestion_id, {"waiting", "failed"})
    title, caption = title.strip(), caption.strip()
    hashtags = social.get_settings(session).fixed_hashtags
    problems = post_ai.text_problems(title, caption, hashtags)
    if problems:
        raise ReviewError("The post needs " + ", ".join(problems) + ".")
    usable = _usable(suggestion.weekly_update)
    if chosen_medium_id not in {medium.id for medium in usable}:
        raise ReviewError("Choose one of this week's photos or its video.")
    suggestion.title, suggestion.caption = title, caption
    suggestion.chosen_medium_id = chosen_medium_id
    if not suggestion.ranking:
        suggestion.ranking = [medium.id for medium in usable]
    suggestion.state = "waiting"
    suggestion.last_error = None
    mark_reviewed(session, suggestion, reviewer)
    session.commit()
    return suggestion


def refuse(
    session: Session, reviewer: User, suggestion_id: int, reason: str | None
) -> PostSuggestion:
    """No post for this Project this Upload week; the team sees the reason."""
    suggestion = locked(session, suggestion_id, {"waiting", "failed"})
    suggestion.state = "refused"
    suggestion.refusal_reason = (reason or "").strip()[:500] or None
    mark_reviewed(session, suggestion, reviewer)
    session.commit()
    return suggestion


def generate_again(
    session: Session, reviewer: User, suggestion_id: int
) -> PostSuggestion:
    """Let the AI start over; `attempt_now` then makes it at once."""
    suggestion = locked(session, suggestion_id, {"waiting", "failed", "refused"})
    suggestion.state = "generating"
    suggestion.attempts = 0
    suggestion.next_attempt_at = None
    suggestion.last_error = None
    suggestion.refusal_reason = None
    mark_reviewed(session, suggestion, reviewer)
    session.commit()
    return suggestion


def attempt_now(
    make_session: Callable[[], Session], llm: LLM, media_dir: Path, suggestion_id: int
) -> None:
    """One try right away (after Generate again), without waiting for the job."""
    with make_session() as session:
        attempt(session, llm, media_dir, suggestion_id, datetime.now(BRUSSELS))
