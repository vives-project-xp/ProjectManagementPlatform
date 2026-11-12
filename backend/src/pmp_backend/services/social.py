"""Social media (spec #110): the Superuser's settings and the Weekly updates
that teams write each Upload week."""

import re
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from pmp_backend.errors import Refused
from pmp_backend.models import SocialSettings, User, WeeklyUpdate
from pmp_backend.services.projects import get_project

BRUSSELS = ZoneInfo("Europe/Brussels")

DEFAULT_INSTAGRAM_WEEKDAYS = [0, 1, 2, 3, 4]
DEFAULT_INSTAGRAM_TIMES = ["12:00", "19:00"]
DEFAULT_FIXED_HASHTAGS = "#VIVEShogeschool #ElektronicaICT"
# At most two posts a day on a Channel (Q14).
MAX_POSTING_TIMES = 2
MAX_HASHTAGS = 10
MAX_UPDATE_LENGTH = 4000
_HASHTAG = re.compile(r"#\w+")


class SocialError(Refused):
    """A social media change was refused; the message is fit to show."""


@dataclass(frozen=True)
class Settings:
    """The Upload deadline (both None until set), Instagram's Posting times and
    the Fixed hashtags."""

    upload_weekday: int | None
    upload_time: time | None
    instagram_weekdays: list[int]
    instagram_times: list[str]
    fixed_hashtags: str


def get_settings(session: Session) -> Settings:
    row = session.get(SocialSettings, 1)
    if row is None:
        return Settings(
            upload_weekday=None,
            upload_time=None,
            instagram_weekdays=DEFAULT_INSTAGRAM_WEEKDAYS,
            instagram_times=DEFAULT_INSTAGRAM_TIMES,
            fixed_hashtags=DEFAULT_FIXED_HASHTAGS,
        )
    return Settings(
        upload_weekday=row.upload_weekday,
        upload_time=row.upload_time,
        instagram_weekdays=row.instagram_weekdays,
        instagram_times=row.instagram_times,
        fixed_hashtags=row.fixed_hashtags,
    )


def _check_hashtags(text: str) -> str:
    words = text.split()
    if not words or len(words) > MAX_HASHTAGS:
        raise SocialError(f"Give between 1 and {MAX_HASHTAGS} Fixed hashtags.")
    for word in words:
        if not _HASHTAG.fullmatch(word):
            raise SocialError(
                f'"{word}" is not a hashtag: start with # and use letters, '
                "digits or _ only."
            )
    return " ".join(words)


def set_settings(
    session: Session,
    *,
    upload_weekday: int | None,
    upload_time: time | None,
    instagram_weekdays: list[int],
    instagram_times: list[str],
    fixed_hashtags: str,
) -> Settings:
    """Save the settings. A changed Upload deadline closes the open Upload week
    at the next moment matching the new deadline."""
    if (upload_weekday is None) != (upload_time is None):
        raise SocialError("Give the Upload deadline's weekday and time together.")
    if not instagram_weekdays:
        raise SocialError("Choose at least one weekday for Instagram.")
    times = sorted(set(instagram_times))
    if not 1 <= len(times) <= MAX_POSTING_TIMES:
        raise SocialError(f"Give 1 or {MAX_POSTING_TIMES} Posting times for Instagram.")
    hashtags = _check_hashtags(fixed_hashtags)
    # Locked until commit, so two changes cannot interleave.
    row = session.scalar(select(SocialSettings).with_for_update())
    if row is None:
        row = SocialSettings(id=1)
        session.add(row)
    deadline_changed = (row.upload_weekday, row.upload_time) != (
        upload_weekday,
        upload_time,
    )
    row.upload_weekday = upload_weekday
    row.upload_time = upload_time
    row.instagram_weekdays = sorted(set(instagram_weekdays))
    row.instagram_times = times
    row.fixed_hashtags = hashtags
    if deadline_changed and upload_weekday is not None:
        now = _now(session)
        session.execute(
            update(WeeklyUpdate)
            .where(WeeklyUpdate.closes_at > now)
            .values(closes_at=next_close(upload_weekday, upload_time, now))
        )
    session.commit()
    return get_settings(session)


def next_close(weekday: int, at: time, now: datetime) -> datetime:
    """The first moment after `now` matching the deadline, in Belgian time."""
    local = now.astimezone(BRUSSELS)
    day = local.date() + timedelta(days=(weekday - local.weekday()) % 7)
    moment = datetime.combine(day, at, BRUSSELS)
    if moment <= local:
        moment = datetime.combine(day + timedelta(days=7), at, BRUSSELS)
    return moment


def _now(session: Session) -> datetime:
    # The database's clock, like every other timestamp.
    return session.scalar(select(func.now()))


def open_week(session: Session) -> datetime | None:
    """When the open Upload week closes; None until the deadline is set."""
    settings = get_settings(session)
    if settings.upload_weekday is None:
        return None
    return next_close(settings.upload_weekday, settings.upload_time, _now(session))


# Weekly updates


@dataclass(frozen=True)
class WeekView:
    """A Project's Weekly update of one Upload week (text empty when nobody
    wrote one yet), and whether that week is still open."""

    closes_at: datetime
    text: str
    edited_by: str | None
    edited_at: datetime | None
    is_open: bool


def _view(update_: WeeklyUpdate, now: datetime) -> WeekView:
    return WeekView(
        closes_at=update_.closes_at,
        text=update_.text,
        edited_by=update_.edited_by.full_name if update_.edited_by else "Deleted user",
        edited_at=update_.edited_at,
        is_open=update_.closes_at > now,
    )


def weekly_updates(session: Session, project_id: int) -> list[WeekView]:
    """Every Weekly update of a Project, newest first."""
    get_project(session, project_id)
    now = _now(session)
    found = session.scalars(
        select(WeeklyUpdate)
        .where(WeeklyUpdate.project_id == project_id)
        .order_by(WeeklyUpdate.closes_at.desc())
    )
    return [_view(update_, now) for update_ in found]


@dataclass(frozen=True)
class MyWeeklyUpdate:
    """A Member's view: the open Upload week (None until the deadline is set)
    and the earlier ones, newest first."""

    current: WeekView | None
    earlier: list[WeekView]


def my_weekly_update(session: Session, student: User) -> MyWeeklyUpdate:
    if student.project_id is None:
        raise SocialError("You're not in a Project.")
    closes_at = open_week(session)
    updates = weekly_updates(session, student.project_id)
    if closes_at is None:
        return MyWeeklyUpdate(current=None, earlier=updates)
    current = next((u for u in updates if u.closes_at == closes_at), None)
    if current is None:
        current = WeekView(
            closes_at=closes_at, text="", edited_by=None, edited_at=None, is_open=True
        )
    return MyWeeklyUpdate(
        current=current, earlier=[u for u in updates if u.closes_at < closes_at]
    )


def save_weekly_update(session: Session, student: User, text: str) -> MyWeeklyUpdate:
    """Write the team's Weekly update of the open Upload week; earlier weeks
    are locked."""
    if student.project_id is None:
        raise SocialError("You're not in a Project.")
    text = text.strip()
    if len(text) > MAX_UPDATE_LENGTH:
        raise SocialError(
            f"The Weekly update can be at most {MAX_UPDATE_LENGTH} characters."
        )
    closes_at = open_week(session)
    if closes_at is None:
        raise SocialError("The Upload deadline hasn't been set yet.")
    # Two Members saving at once: the last one wins, without a duplicate row.
    session.execute(
        insert(WeeklyUpdate)
        .values(
            project_id=student.project_id,
            closes_at=closes_at,
            text=text,
            edited_by_id=student.id,
        )
        .on_conflict_do_update(
            constraint="uq_weekly_updates_project_week",
            set_={"text": text, "edited_by_id": student.id, "edited_at": func.now()},
        )
    )
    session.commit()
    return my_weekly_update(session, student)
