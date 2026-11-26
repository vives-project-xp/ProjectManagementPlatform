"""Social media (spec #110): the Superuser's settings and the Weekly updates
that teams write each Upload week."""

import asyncio
import logging
import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from pmp_backend.domain import Role
from pmp_backend.errors import Forbidden, NotFound, Refused
from pmp_backend.models import (
    PostSuggestion,
    PublishLink,
    SocialSettings,
    TikTokPost,
    User,
    WeeklyMedium,
    WeeklySlideshow,
    WeeklySlideshowPhoto,
    WeeklyUpdate,
)
from pmp_backend.services import clients, media, video
from pmp_backend.services.projects import get_project

BRUSSELS = ZoneInfo("Europe/Brussels")

DEFAULT_INSTAGRAM_WEEKDAYS = [0, 1, 2, 3, 4]
DEFAULT_INSTAGRAM_TIMES = ["12:00", "19:00"]
DEFAULT_FIXED_HASHTAGS = "#VIVEShogeschool #ElektronicaICT"
# TikTok (spec #145): videos Monday-Friday 17:00, the Weekly slideshow on
# Friday 18:00, put together at Friday 12:00.
DEFAULT_TIKTOK_WEEKDAYS = [0, 1, 2, 3, 4]
DEFAULT_TIKTOK_TIMES = ["17:00"]
DEFAULT_SLIDESHOW = (4, time(18, 0))
DEFAULT_SLIDESHOW_CUTOFF = (4, time(12, 0))
# At most two posts a day on a Channel (Q14).
MAX_POSTING_TIMES = 2
MAX_HASHTAGS = 10
MAX_UPDATE_LENGTH = 4000
_HASHTAG = re.compile(r"#\w+")


class SocialError(Refused):
    """A social media change was refused; the message is fit to show."""


class SocialNotFoundError(SocialError, NotFound):
    pass


class SocialForbiddenError(SocialError, Forbidden):
    pass


@dataclass(frozen=True)
class Settings:
    """The Upload deadline (both None until set), Instagram's Posting times,
    the Fixed hashtags, TikTok's Posting times and the Weekly slideshow's
    Posting time and cut-off."""

    upload_weekday: int | None
    upload_time: time | None
    instagram_weekdays: list[int]
    instagram_times: list[str]
    fixed_hashtags: str
    tiktok_weekdays: list[int]
    tiktok_times: list[str]
    slideshow_weekday: int
    slideshow_time: time
    slideshow_cutoff_weekday: int
    slideshow_cutoff_time: time


def get_settings(session: Session) -> Settings:
    row = session.get(SocialSettings, 1)
    if row is None:
        return Settings(
            upload_weekday=None,
            upload_time=None,
            instagram_weekdays=DEFAULT_INSTAGRAM_WEEKDAYS,
            instagram_times=DEFAULT_INSTAGRAM_TIMES,
            fixed_hashtags=DEFAULT_FIXED_HASHTAGS,
            tiktok_weekdays=DEFAULT_TIKTOK_WEEKDAYS,
            tiktok_times=DEFAULT_TIKTOK_TIMES,
            slideshow_weekday=DEFAULT_SLIDESHOW[0],
            slideshow_time=DEFAULT_SLIDESHOW[1],
            slideshow_cutoff_weekday=DEFAULT_SLIDESHOW_CUTOFF[0],
            slideshow_cutoff_time=DEFAULT_SLIDESHOW_CUTOFF[1],
        )
    return Settings(
        upload_weekday=row.upload_weekday,
        upload_time=row.upload_time,
        instagram_weekdays=row.instagram_weekdays,
        instagram_times=row.instagram_times,
        fixed_hashtags=row.fixed_hashtags,
        tiktok_weekdays=row.tiktok_weekdays,
        tiktok_times=row.tiktok_times,
        slideshow_weekday=row.slideshow_weekday,
        slideshow_time=row.slideshow_time,
        slideshow_cutoff_weekday=row.slideshow_cutoff_weekday,
        slideshow_cutoff_time=row.slideshow_cutoff_time,
    )


def _posting_times(channel: str, weekdays: list[int], times: list[str]):
    if not weekdays:
        raise SocialError(f"Choose at least one weekday for {channel}.")
    unique = sorted(set(times))
    if not 1 <= len(unique) <= MAX_POSTING_TIMES:
        raise SocialError(f"Give 1 or {MAX_POSTING_TIMES} Posting times for {channel}.")
    return sorted(set(weekdays)), unique


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
    tiktok_weekdays: list[int] | None = None,
    tiktok_times: list[str] | None = None,
    slideshow: tuple[int, time] | None = None,
    slideshow_cutoff: tuple[int, time] | None = None,
) -> Settings:
    """Save the settings; TikTok's and the slideshow's are kept when not
    given. A changed Upload deadline closes the open Upload week at the next
    moment matching the new deadline."""
    if (upload_weekday is None) != (upload_time is None):
        raise SocialError("Give the Upload deadline's weekday and time together.")
    instagram_days, times = _posting_times(
        "Instagram", instagram_weekdays, instagram_times
    )
    hashtags = _check_hashtags(fixed_hashtags)
    current = get_settings(session)
    tiktok_days, tiktok_clock = _posting_times(
        "TikTok",
        current.tiktok_weekdays if tiktok_weekdays is None else tiktok_weekdays,
        current.tiktok_times if tiktok_times is None else tiktok_times,
    )
    if slideshow is None:
        slideshow = (current.slideshow_weekday, current.slideshow_time)
    if slideshow_cutoff is None:
        slideshow_cutoff = (
            current.slideshow_cutoff_weekday,
            current.slideshow_cutoff_time,
        )
    # Locked until commit, so two changes cannot interleave.
    row = session.scalar(select(SocialSettings).with_for_update())
    if row is None:
        row = SocialSettings(id=1)
        session.add(row)
    row.tiktok_weekdays = tiktok_days
    row.tiktok_times = tiktok_clock
    row.slideshow_weekday, row.slideshow_time = slideshow
    row.slideshow_cutoff_weekday, row.slideshow_cutoff_time = slideshow_cutoff
    deadline_changed = (row.upload_weekday, row.upload_time) != (
        upload_weekday,
        upload_time,
    )
    row.upload_weekday = upload_weekday
    row.upload_time = upload_time
    row.instagram_weekdays = instagram_days
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
class MediumView:
    """A photo or video of a Weekly update, and who uploaded it."""

    id: int
    kind: str
    # "processing" while a video is being prepared, "failed" when that went
    # wrong, otherwise "ready".
    state: str
    width: int
    height: int
    seconds: float | None
    uploaded_by: str
    uploaded_at: datetime


@dataclass(frozen=True)
class WeekView:
    """A Project's Weekly update of one Upload week (text empty when nobody
    wrote one yet), its Media, and whether that week is still open."""

    closes_at: datetime
    text: str
    edited_by: str | None
    edited_at: datetime | None
    is_open: bool
    media: list[MediumView]
    # The Post suggestion's state once there is one, and why it was refused.
    suggestion_state: str | None = None
    refusal_reason: str | None = None
    # Its Posting time once Posted, and when it was posted by hand (#118) or
    # published, with the post on Instagram (#117).
    scheduled_for: datetime | None = None
    posted_at: datetime | None = None
    published_url: str | None = None
    # Its video on TikTok (#147): the state, and the Posting time or when it
    # was posted.
    tiktok_state: str | None = None
    tiktok_scheduled_for: datetime | None = None
    tiktok_posted_at: datetime | None = None
    # The Posting time of the Weekly slideshow with one of its photos, once
    # that slideshow was Posted (#150).
    slideshow_at: datetime | None = None
    # When the never-posted Media were deleted, 4 months after the week (#118).
    media_removed_at: datetime | None = None


def _name(user: User | None) -> str:
    return user.full_name if user else "Deleted user"


def week_view(update_: WeeklyUpdate, now: datetime) -> WeekView:
    suggestion = update_.suggestion
    tiktok = suggestion.tiktok_post if suggestion else None
    return WeekView(
        closes_at=update_.closes_at,
        text=update_.text,
        edited_by=_name(update_.edited_by),
        edited_at=update_.edited_at,
        is_open=update_.closes_at > now,
        media=[
            MediumView(
                id=medium.id,
                kind=medium.kind,
                state=medium.state,
                width=medium.width,
                height=medium.height,
                seconds=medium.seconds,
                uploaded_by=_name(medium.uploaded_by),
                uploaded_at=medium.uploaded_at,
            )
            for medium in update_.media
        ],
        suggestion_state=suggestion.state if suggestion else None,
        refusal_reason=suggestion.refusal_reason if suggestion else None,
        scheduled_for=suggestion.scheduled_for if suggestion else None,
        posted_at=suggestion.posted_at if suggestion else None,
        published_url=suggestion.published_url if suggestion else None,
        tiktok_state=tiktok.state if tiktok else None,
        tiktok_scheduled_for=tiktok.scheduled_for if tiktok else None,
        tiktok_posted_at=tiktok.posted_at if tiktok else None,
        slideshow_at=next(
            (
                photo.slideshow.scheduled_for
                for medium in update_.media
                for photo in medium.slideshow_photos
                if photo.slideshow.state in _SLIDESHOW_POSTED
            ),
            None,
        ),
        media_removed_at=update_.media_removed_at,
    )


def weekly_updates(session: Session, project_id: int) -> list[WeekView]:
    """Every Weekly update of a Project, newest first."""
    get_project(session, project_id)
    now = _now(session)
    found = session.scalars(
        select(WeeklyUpdate)
        .where(WeeklyUpdate.project_id == project_id)
        .order_by(WeeklyUpdate.closes_at.desc())
        # Fresh text and Media, also right after a change in this session.
        .execution_options(populate_existing=True)
    )
    return [week_view(update_, now) for update_ in found]


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
            closes_at=closes_at,
            text="",
            edited_by=None,
            edited_at=None,
            is_open=True,
            media=[],
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


# Media (photos since #112, the video since #113)

log = logging.getLogger(__name__)

MAX_PHOTOS = 5
MAX_PHOTO_BYTES = 15 * 1024 * 1024
MAX_VIDEO_BYTES = 200 * 1024 * 1024
# Above this share of the disk in use, staff see a warning.
DISK_WARNING = 0.80
NO_MEDIUM = "This photo or video doesn't exist (any more)."


def _open_update(session: Session, student: User) -> WeeklyUpdate:
    """The team's Weekly update of the open Upload week, created empty if
    needed and locked until commit (so the photo limit holds)."""
    if student.project_id is None:
        raise SocialError("You're not in a Project.")
    closes_at = open_week(session)
    if closes_at is None:
        raise SocialError("The Upload deadline hasn't been set yet.")
    session.execute(
        insert(WeeklyUpdate)
        .values(
            project_id=student.project_id,
            closes_at=closes_at,
            text="",
            edited_by_id=student.id,
        )
        .on_conflict_do_nothing(constraint="uq_weekly_updates_project_week")
    )
    return session.scalars(
        select(WeeklyUpdate)
        .where(
            WeeklyUpdate.project_id == student.project_id,
            WeeklyUpdate.closes_at == closes_at,
        )
        .with_for_update(of=WeeklyUpdate)
        .execution_options(populate_existing=True)
    ).one()


def medium_path(
    media_dir: Path, project_id: int, medium: WeeklyMedium, copy: str = ""
) -> Path:
    """A medium's file: the photo, or the video's posted copy; `copy` "ai" is
    the video's small copy for the AI, "original" the upload until processed.
    Never the uploaded name, so nothing outside the folder can be written."""
    if medium.kind == "photo":
        name = f"{medium.id}.jpg"
    elif copy:
        name = f"{medium.id}.{copy}" + (".mp4" if copy == "ai" else "")
    else:
        name = f"{medium.id}.mp4"
    return media_dir / str(project_id) / name


def _all_files(media_dir: Path, project_id: int, medium: WeeklyMedium) -> list[Path]:
    return [
        medium_path(media_dir, project_id, medium, copy)
        for copy in ("", "ai", "original")
    ]


def incoming_path(media_dir: Path, name: str) -> Path:
    """Where an upload is written before it is checked."""
    folder = media_dir / "incoming"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / name


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Written under another name first, so a failed write leaves no file.
    partial = path.with_name(f"{path.name}.partial")
    partial.write_bytes(data)
    partial.replace(path)


def upload_photo(
    session: Session, media_dir: Path, student: User, data: bytes, *, consent: bool
) -> MyWeeklyUpdate:
    """Add a photo to the team's open Weekly update after the Consent tick and
    the Quality check; refused photos are never stored or counted."""
    if not consent:
        raise SocialError(
            "First tick that everyone recognisable in your photos agrees to them "
            "being posted on VIVES social media."
        )
    if len(data) > MAX_PHOTO_BYTES:
        raise SocialError("This photo is larger than 15 MB.")
    # Checked before locking the Weekly update: decoding takes a moment.
    photo = media.check_photo(data)
    update_ = _open_update(session, student)
    photos = [medium for medium in update_.media if medium.kind == "photo"]
    if len(photos) >= MAX_PHOTOS:
        raise SocialError(
            f"Your team already has {MAX_PHOTOS} photos this week. Remove one first."
        )
    medium = WeeklyMedium(
        weekly_update_id=update_.id,
        kind="photo",
        size=len(photo.jpeg),
        width=photo.width,
        height=photo.height,
        quality_score=photo.score,
        uploaded_by_id=student.id,
    )
    session.add(medium)
    session.flush()
    path = medium_path(media_dir, update_.project_id, medium)
    _write(path, photo.jpeg)
    try:
        session.commit()
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return my_weekly_update(session, student)


def _medium(session: Session, medium_id: int) -> tuple[WeeklyMedium, WeeklyUpdate]:
    medium = session.get(WeeklyMedium, medium_id)
    if medium is None:
        raise SocialNotFoundError(NO_MEDIUM)
    return medium, session.get(WeeklyUpdate, medium.weekly_update_id)


def remove_medium(
    session: Session, media_dir: Path, student: User, medium_id: int
) -> MyWeeklyUpdate:
    """Remove a photo or video of the team's open Weekly update."""
    medium, update_ = _medium(session, medium_id)
    if update_.project_id != student.project_id:
        raise SocialNotFoundError(NO_MEDIUM)
    if update_.closes_at <= _now(session):
        raise SocialError("This Upload week has closed, so its media are locked.")
    paths = _all_files(media_dir, update_.project_id, medium)
    session.delete(medium)
    session.commit()
    for path in paths:
        path.unlink(missing_ok=True)
    return my_weekly_update(session, student)


def read_medium(
    session: Session, media_dir: Path, user: User, medium_id: int
) -> tuple[WeeklyMedium, Path]:
    """A photo or video (its posted copy) for the Project's Members and
    Clients (#135), Teachers and the Superuser."""
    medium, update_ = _medium(session, medium_id)
    if user.role == Role.STUDENT and user.project_id != update_.project_id:
        raise SocialForbiddenError("Only the Project's Members can see its media.")
    if user.role == Role.CLIENT and not clients.follows(
        session, user, update_.project_id
    ):
        raise SocialForbiddenError("Only the Project's Members can see its media.")
    if medium.state != "ready":
        raise SocialNotFoundError("This video isn't ready yet.")
    path = medium_path(media_dir, update_.project_id, medium)
    if not path.is_file():
        raise SocialNotFoundError(NO_MEDIUM)
    return medium, path


def discard_media(media_dir: Path, project_id: int) -> None:
    """Delete the media files of a deleted Project."""
    shutil.rmtree(media_dir / str(project_id), ignore_errors=True)


# The 4-month clean-up (#118)

# About 4 months, like the Chat's 182 days for 6.
KEEP_MEDIA = timedelta(days=122)
CLEAN_UP_EVERY_SECONDS = 24 * 60 * 60
# A post still on its way to Instagram keeps its week's Media.
_STILL_TO_POST = ("scheduled", "to_post_by_hand")
_SLIDESHOW_POSTED = ("scheduled", "in_inbox", "to_post_by_hand", "posted")


def clean_up(session: Session, media_dir: Path, now: datetime) -> list[int]:
    """Delete the never-posted Media of Upload weeks that closed more than
    KEEP_MEDIA before `now`; posted Media stay. The week keeps its text and
    outcome and remembers when its Media went. Expired Publish links (#117) go
    too. The ids of the cleaned weeks."""
    session.execute(delete(PublishLink).where(PublishLink.expires_at <= now))
    expired = session.scalars(
        select(WeeklyUpdate)
        .where(
            WeeklyUpdate.closes_at < now - KEEP_MEDIA,
            select(WeeklyMedium.id)
            .where(
                WeeklyMedium.weekly_update_id == WeeklyUpdate.id,
                WeeklyMedium.posted.is_(False),
            )
            .exists(),
            ~select(PostSuggestion.id)
            .where(
                PostSuggestion.weekly_update_id == WeeklyUpdate.id,
                PostSuggestion.state.in_(_STILL_TO_POST),
            )
            .exists(),
            # Nor while a photo waits in a Weekly slideshow (#150).
            ~select(WeeklySlideshowPhoto.medium_id)
            .join(WeeklyMedium, WeeklyMedium.id == WeeklySlideshowPhoto.medium_id)
            .join(
                WeeklySlideshow,
                WeeklySlideshow.id == WeeklySlideshowPhoto.slideshow_id,
            )
            .where(
                WeeklyMedium.weekly_update_id == WeeklyUpdate.id,
                WeeklySlideshow.state.in_(("scheduled", "in_inbox", "to_post_by_hand")),
            )
            .exists(),
            # Nor while its video still waits for TikTok (#147).
            ~select(TikTokPost.id)
            .join(PostSuggestion, PostSuggestion.id == TikTokPost.suggestion_id)
            .where(
                PostSuggestion.weekly_update_id == WeeklyUpdate.id,
                TikTokPost.state.in_(_STILL_TO_POST),
            )
            .exists(),
        )
        .with_for_update(of=WeeklyUpdate, skip_locked=True)
        .execution_options(populate_existing=True)
    ).all()
    paths: list[Path] = []
    for update_ in expired:
        for medium in update_.media:
            if not medium.posted:
                paths += _all_files(media_dir, update_.project_id, medium)
                session.delete(medium)
        update_.media_removed_at = now
    session.commit()
    # Files go after the commit, so a failed commit never loses a kept medium.
    for path in paths:
        path.unlink(missing_ok=True)
    return [update_.id for update_ in expired]


async def clean_up_forever(
    make_session: Callable[[], Session], media_dir: Path
) -> None:
    """Once a day, the 4-month clean-up; never crashes the backend."""

    def run_once() -> None:
        with make_session() as session:
            cleaned = clean_up(session, media_dir, _now(session))
        if cleaned:
            log.info("Removed the never-posted media of Weekly updates %s", cleaned)

    while True:
        try:
            await asyncio.to_thread(run_once)
        except Exception:
            log.exception("The social media clean-up failed")
        await asyncio.sleep(CLEAN_UP_EVERY_SECONDS)


def upload_video(
    session: Session, media_dir: Path, student: User, upload: Path, *, consent: bool
) -> tuple[MyWeeklyUpdate, int]:
    """Add the team's one video of the open Upload week from `upload` (a file
    in the incoming folder, moved away or deleted here). It is "processing"
    until `process_video` with the returned id has made its copies."""
    try:
        if not consent:
            raise SocialError(
                "First tick that everyone recognisable in your video agrees to it "
                "being posted on VIVES social media."
            )
        if upload.stat().st_size > MAX_VIDEO_BYTES:
            raise SocialError("This video is larger than 200 MB.")
        # Checked before locking the Weekly update: reading it takes a moment.
        found = video.check(upload)
        update_ = _open_update(session, student)
        if any(medium.kind == "video" for medium in update_.media):
            raise SocialError(
                "Your team already has a video this week. Remove it first."
            )
        medium = WeeklyMedium(
            weekly_update_id=update_.id,
            kind="video",
            state="processing",
            size=upload.stat().st_size,
            width=found.width,
            height=found.height,
            seconds=found.seconds,
            uploaded_by_id=student.id,
        )
        session.add(medium)
        session.flush()
        original = medium_path(media_dir, update_.project_id, medium, "original")
        original.parent.mkdir(parents=True, exist_ok=True)
        upload.replace(original)
        try:
            session.commit()
        except Exception:
            original.unlink(missing_ok=True)
            raise
    finally:
        upload.unlink(missing_ok=True)
    return my_weekly_update(session, student), medium.id


def process_video(
    make_session: Callable[[], Session], media_dir: Path, medium_id: int
) -> None:
    """Make the posted copy and the AI copy of an uploaded video, then delete
    the original; runs in the background after the upload."""
    with make_session() as session:
        medium = session.get(WeeklyMedium, medium_id)
        if medium is None or medium.state != "processing":
            return
        project_id = session.get(WeeklyUpdate, medium.weekly_update_id).project_id
        original, posted, for_ai = (
            medium_path(media_dir, project_id, medium, copy)
            for copy in ("original", "", "ai")
        )
    try:
        made = video.encode(original, posted, for_ai)
        state = "ready"
    except (OSError, subprocess.SubprocessError, video.VideoRefused):
        log.exception("Processing video %s failed", medium_id)
        posted.unlink(missing_ok=True)
        for_ai.unlink(missing_ok=True)
        made, state = None, "failed"
    original.unlink(missing_ok=True)
    with make_session() as session:
        medium = session.get(WeeklyMedium, medium_id)
        if medium is None:
            # Removed while it was being processed.
            posted.unlink(missing_ok=True)
            for_ai.unlink(missing_ok=True)
            return
        medium.state = state
        if made is not None:
            medium.width, medium.height = made.width, made.height
            medium.size = posted.stat().st_size
        session.commit()


def resume_processing(make_session: Callable[[], Session], media_dir: Path) -> None:
    """Process the videos whose processing a restart interrupted."""
    with make_session() as session:
        waiting = session.scalars(
            select(WeeklyMedium.id).where(WeeklyMedium.state == "processing")
        ).all()
    for medium_id in waiting:
        process_video(make_session, media_dir, medium_id)


@dataclass(frozen=True)
class Storage:
    """How full the disk with the media is."""

    used_share: float

    @property
    def warning(self) -> bool:
        return self.used_share > DISK_WARNING


def storage(media_dir: Path) -> Storage:
    media_dir.mkdir(parents=True, exist_ok=True)
    usage = shutil.disk_usage(media_dir)
    return Storage(used_share=usage.used / usage.total)
