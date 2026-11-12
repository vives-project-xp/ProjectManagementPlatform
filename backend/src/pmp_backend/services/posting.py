"""Posting reviewed suggestions (spec #110, #116): Post puts a suggestion in
Instagram's line; each gets the next free Posting time, in the order they were
Posted, never the same Project twice in a row. At its Posting time it moves to
the To post today list, where a person publishes it by hand (automatic
publishing comes with #117)."""

import asyncio
import logging
from collections.abc import Callable, Iterator
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from pmp_backend.models import PostSuggestion, User, WeeklyMedium, WeeklyUpdate
from pmp_backend.services import social
from pmp_backend.services.suggestions import (
    ReviewConflictError,
    locked,
    mark_reviewed,
)

log = logging.getLogger(__name__)

BRUSSELS = ZoneInfo("Europe/Brussels")
# A post is never given a Posting time that is closer than this, and one that
# is this close keeps its time when the line changes.
MARGIN = timedelta(minutes=10)
# How far ahead Posting times are looked for.
HORIZON_DAYS = 120
EVERY_SECONDS = 60


def posting_times(
    weekdays: list[int], times: list[str], after: datetime
) -> Iterator[datetime]:
    """The Posting times after `after`, in order (Belgian time)."""
    local = after.astimezone(BRUSSELS)
    clock = sorted(time.fromisoformat(value) for value in times)
    for offset in range(HORIZON_DAYS):
        day = local.date() + timedelta(days=offset)
        if day.weekday() not in weekdays:
            continue
        for at in clock:
            moment = datetime.combine(day, at, BRUSSELS)
            if moment > after:
                yield moment


def _now(session: Session) -> datetime:
    return session.scalar(select(func.now()))


def _project_of(suggestion: PostSuggestion) -> int:
    return suggestion.weekly_update.project_id


def plan(session: Session) -> None:
    """Give every Scheduled post a Posting time again: first free times from
    now on, in the order they were Posted, never the same Project twice in a
    row (a post then swaps with the next one). Posts due within the margin keep
    their time."""
    now = _now(session)
    scheduled = session.scalars(
        select(PostSuggestion)
        .where(PostSuggestion.state == "scheduled")
        .order_by(PostSuggestion.queued_at, PostSuggestion.id)
        .with_for_update(of=PostSuggestion)
    ).all()
    fixed = [
        s for s in scheduled if s.scheduled_for and s.scheduled_for <= now + MARGIN
    ]
    line = [s for s in scheduled if s not in fixed]
    taken = {s.scheduled_for for s in fixed}
    # The last post before the line, so the line doesn't start with its Project.
    before = session.scalar(
        select(PostSuggestion)
        .where(
            PostSuggestion.scheduled_for.is_not(None),
            PostSuggestion.state != "scheduled",
        )
        .order_by(PostSuggestion.scheduled_for.desc())
        .limit(1)
    )
    previous = (
        _project_of(fixed[-1]) if fixed else (_project_of(before) if before else None)
    )
    settings = social.get_settings(session)
    times = (
        moment
        for moment in posting_times(
            settings.instagram_weekdays, settings.instagram_times, now + MARGIN
        )
        if moment not in taken
    )
    while line:
        pick = next((s for s in line if _project_of(s) != previous), line[0])
        line.remove(pick)
        pick.scheduled_for = next(times, None)
        previous = _project_of(pick)
    session.flush()


def post(session: Session, reviewer: User, suggestion_id: int) -> PostSuggestion:
    """Accept a reviewed suggestion: it joins the end of Instagram's line."""
    suggestion = locked(session, suggestion_id, {"waiting"})
    if suggestion.chosen_medium_id is None:
        raise ReviewConflictError("Choose the photo or video to post first.")
    suggestion.state = "scheduled"
    suggestion.queued_at = _now(session)
    mark_reviewed(session, suggestion, reviewer)
    plan(session)
    session.commit()
    return suggestion


def pull_back(session: Session, reviewer: User, suggestion_id: int) -> PostSuggestion:
    """Take a Scheduled post out of the line, back to Review."""
    suggestion = locked(session, suggestion_id, {"scheduled"})
    suggestion.state = "waiting"
    suggestion.queued_at = suggestion.scheduled_for = None
    mark_reviewed(session, suggestion, reviewer)
    plan(session)
    session.commit()
    return suggestion


def mark_posted(session: Session, user: User, suggestion_id: int) -> PostSuggestion:
    """Someone published it by hand; its medium is kept as posted."""
    suggestion = locked(session, suggestion_id, {"to_post_by_hand"})
    suggestion.state = "posted_by_hand"
    suggestion.posted_by_id = user.id
    suggestion.posted_at = _now(session)
    medium = session.get(WeeklyMedium, suggestion.chosen_medium_id)
    if medium is not None:
        medium.posted = True
    session.commit()
    return suggestion


def run_once(session: Session, now: datetime) -> list[int]:
    """Posts whose Posting time has come go to the To post today list."""
    due = session.scalars(
        select(PostSuggestion)
        .where(
            PostSuggestion.state == "scheduled",
            PostSuggestion.scheduled_for <= now,
        )
        .with_for_update(of=PostSuggestion)
    ).all()
    for suggestion in due:
        suggestion.state = "to_post_by_hand"
    session.commit()
    return [suggestion.id for suggestion in due]


async def run_forever(make_session: Callable[[], Session]) -> None:
    def run() -> None:
        with make_session() as session:
            run_once(session, datetime.now(BRUSSELS))

    while True:
        try:
            await asyncio.to_thread(run)
        except Exception:
            # A failing round is logged; the next one tries again.
            log.exception("Moving due posts failed")
        await asyncio.sleep(EVERY_SECONDS)


def lists(session: Session) -> tuple[list[int], list[int]]:
    """The ids To post today (oldest first) and Scheduled (soonest first)."""
    to_post = session.scalars(
        select(PostSuggestion.id)
        .where(PostSuggestion.state == "to_post_by_hand")
        .order_by(PostSuggestion.scheduled_for)
    ).all()
    scheduled = session.scalars(
        select(PostSuggestion.id)
        .join(WeeklyUpdate, WeeklyUpdate.id == PostSuggestion.weekly_update_id)
        .where(PostSuggestion.state == "scheduled")
        .order_by(PostSuggestion.scheduled_for)
    ).all()
    return list(to_post), list(scheduled)
