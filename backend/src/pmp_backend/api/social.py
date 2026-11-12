import shutil
import uuid
from datetime import datetime, time
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    File,
    Form,
    Request,
    Response,
    UploadFile,
)
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, StringConstraints

from pmp_backend.api.deps import (
    CurrentUserDep,
    SessionDep,
    SettingsDep,
    StudentDep,
    SuperuserDep,
    TeacherOrSuperuserDep,
)
from pmp_backend.api.schemas import ProjectRefOut
from pmp_backend.services import post_ai, social, suggestions
from pmp_backend.services.social import MyWeeklyUpdate, WeekView

router = APIRouter(prefix="/api", tags=["social"])

# "HH:MM", Belgian time.
ClockTime = Annotated[str, StringConstraints(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")]
Weekday = Annotated[int, Field(ge=0, le=6)]


class SocialSettingsOut(BaseModel):
    # Weekday 0 is Monday; both null until the Superuser sets the deadline.
    upload_weekday: int | None
    upload_time: str | None
    instagram_weekdays: list[int]
    instagram_times: list[str]
    fixed_hashtags: str

    @classmethod
    def of(cls, settings: social.Settings) -> "SocialSettingsOut":
        return cls(
            upload_weekday=settings.upload_weekday,
            upload_time=settings.upload_time.strftime("%H:%M")
            if settings.upload_time
            else None,
            instagram_weekdays=settings.instagram_weekdays,
            instagram_times=settings.instagram_times,
            fixed_hashtags=settings.fixed_hashtags,
        )


class SocialSettingsIn(BaseModel):
    upload_weekday: Weekday | None
    upload_time: ClockTime | None
    instagram_weekdays: list[Weekday]
    instagram_times: list[ClockTime]
    fixed_hashtags: str


@router.get("/social/settings")
def get_settings(session: SessionDep, user: SuperuserDep) -> SocialSettingsOut:
    return SocialSettingsOut.of(social.get_settings(session))


@router.put("/social/settings")
def set_settings(
    body: SocialSettingsIn, session: SessionDep, user: SuperuserDep
) -> SocialSettingsOut:
    return SocialSettingsOut.of(
        social.set_settings(
            session,
            upload_weekday=body.upload_weekday,
            upload_time=time.fromisoformat(body.upload_time)
            if body.upload_time
            else None,
            instagram_weekdays=body.instagram_weekdays,
            instagram_times=body.instagram_times,
            fixed_hashtags=body.fixed_hashtags,
        )
    )


class MediumOut(BaseModel):
    id: int
    # "photo" or "video"; the file is GET /api/weekly-media/{id}.
    kind: str
    # "processing" while a video is being prepared, "failed" when that went
    # wrong, otherwise "ready".
    state: str
    width: int
    height: int
    seconds: float | None
    uploaded_by: str
    uploaded_at: datetime


class WeeklyUpdateOut(BaseModel):
    closes_at: datetime
    text: str
    # Null while nobody wrote this week's update yet.
    edited_by: str | None
    edited_at: datetime | None
    is_open: bool
    media: list[MediumOut]

    @classmethod
    def of(cls, week: WeekView) -> "WeeklyUpdateOut":
        return cls(**vars(week) | {"media": [MediumOut(**vars(m)) for m in week.media]})


class MyWeeklyUpdateOut(BaseModel):
    project: ProjectRefOut
    # The open Upload week; null until the Superuser sets the Upload deadline.
    current: WeeklyUpdateOut | None
    earlier: list[WeeklyUpdateOut]


class WeeklyUpdateIn(BaseModel):
    text: str


def _mine(student, found: MyWeeklyUpdate) -> MyWeeklyUpdateOut:
    return MyWeeklyUpdateOut(
        project=ProjectRefOut(id=student.project.id, title=student.project.title),
        current=WeeklyUpdateOut.of(found.current) if found.current else None,
        earlier=[WeeklyUpdateOut.of(week) for week in found.earlier],
    )


@router.get("/my-weekly-update")
def my_weekly_update(
    session: SessionDep, student: StudentDep
) -> MyWeeklyUpdateOut | None:
    """The Member's open Weekly update and earlier ones; None without a Project."""
    if student.project is None:
        return None
    return _mine(student, social.my_weekly_update(session, student))


@router.put("/my-weekly-update")
def save_weekly_update(
    body: WeeklyUpdateIn, session: SessionDep, student: StudentDep
) -> MyWeeklyUpdateOut:
    found = social.save_weekly_update(session, student, body.text)
    return _mine(student, found)


@router.get("/projects/{project_id}/weekly-updates")
def project_weekly_updates(
    project_id: int, session: SessionDep, user: TeacherOrSuperuserDep
) -> list[WeeklyUpdateOut]:
    return [
        WeeklyUpdateOut.of(week) for week in social.weekly_updates(session, project_id)
    ]


@router.post("/my-weekly-update/photos")
def upload_photo(
    session: SessionDep,
    settings: SettingsDep,
    student: StudentDep,
    photo: Annotated[UploadFile, File()],
    consent: Annotated[bool, Form()] = False,
) -> MyWeeklyUpdateOut:
    """A form with one `photo` (JPG, PNG or HEIC, at most 15 MB) and `consent`
    true (the Consent tick)."""
    # One byte more than allowed is enough to know a photo is too large.
    data = photo.file.read(social.MAX_PHOTO_BYTES + 1)
    found = social.upload_photo(
        session, settings.social_media_dir, student, data, consent=consent
    )
    return _mine(student, found)


@router.delete("/my-weekly-update/media/{medium_id}")
def remove_medium(
    medium_id: int, session: SessionDep, settings: SettingsDep, student: StudentDep
) -> MyWeeklyUpdateOut:
    found = social.remove_medium(session, settings.social_media_dir, student, medium_id)
    return _mine(student, found)


@router.get("/weekly-media/{medium_id}")
def get_medium(
    medium_id: int, session: SessionDep, settings: SettingsDep, user: CurrentUserDep
) -> Response:
    """A photo or video for the Project's Members, Teachers and the Superuser."""
    medium, path = social.read_medium(
        session, settings.social_media_dir, user, medium_id
    )
    media_type = "image/jpeg" if medium.kind == "photo" else "video/mp4"
    return FileResponse(
        path, media_type=media_type, headers={"X-Content-Type-Options": "nosniff"}
    )


@router.post("/my-weekly-update/video")
def upload_video(
    request: Request,
    background: BackgroundTasks,
    session: SessionDep,
    settings: SettingsDep,
    student: StudentDep,
    video: Annotated[UploadFile, File()],
    consent: Annotated[bool, Form()] = False,
) -> MyWeeklyUpdateOut:
    """A form with one `video` (MP4 or MOV, at most 200 MB and 90 seconds) and
    `consent` true. It is "processing" until its copies are made."""
    media_dir = settings.social_media_dir
    upload = social.incoming_path(media_dir, uuid.uuid4().hex)
    with upload.open("wb") as target:
        # One byte more than allowed is enough to know a video is too large.
        shutil.copyfileobj(
            _limited(video.file, social.MAX_VIDEO_BYTES + 1), target, 1024 * 1024
        )
    found, medium_id = social.upload_video(
        session, media_dir, student, upload, consent=consent
    )
    background.add_task(
        social.process_video, request.app.state.sessionmaker, media_dir, medium_id
    )
    return _mine(student, found)


class _limited:
    """At most `limit` bytes of `source`, read like a file."""

    def __init__(self, source, limit: int) -> None:
        self._source = source
        self._left = limit

    def read(self, size: int = -1) -> bytes:
        if self._left <= 0:
            return b""
        size = self._left if size < 0 else min(size, self._left)
        data = self._source.read(size)
        self._left -= len(data)
        return data


class StorageOut(BaseModel):
    # The share of the disk in use (0-1), and whether that is above 80%.
    used_share: float
    warning: bool


@router.get("/social/storage")
def get_storage(settings: SettingsDep, user: TeacherOrSuperuserDep) -> StorageOut:
    found = social.storage(settings.social_media_dir)
    return StorageOut(used_share=found.used_share, warning=found.warning)


class SocialStatusOut(BaseModel):
    # Whether LLM_API_KEY is set: without it, no Post suggestions are made.
    ai_configured: bool


@router.get("/social/status")
def get_status(settings: SettingsDep, user: SuperuserDep) -> SocialStatusOut:
    return SocialStatusOut(ai_configured=post_ai.is_configured(settings))


class SuggestionOut(BaseModel):
    id: int
    project: ProjectRefOut
    # The Upload week it is about.
    closes_at: datetime
    # "generating" (the AI is busy, or tries again soon), "waiting" (for
    # Review) or "failed"; later tickets add the Review and posting states.
    state: str
    title: str | None
    caption: str | None
    chosen: MediumOut | None
    # The Media, best first (the chosen one first).
    ranking: list[MediumOut]
    why: str | None
    attempts: int
    last_error: str | None


@router.get("/post-suggestions")
def list_suggestions(
    session: SessionDep, user: TeacherOrSuperuserDep
) -> list[SuggestionOut]:
    found = []
    for view in suggestions.suggestions(session):
        suggestion = view.suggestion

        def medium(medium_id: int | None, view=view) -> MediumOut | None:
            known = view.media.get(medium_id) if medium_id is not None else None
            return MediumOut(**vars(known)) if known else None

        found.append(
            SuggestionOut(
                id=suggestion.id,
                project=ProjectRefOut(id=view.project.id, title=view.project.title),
                closes_at=view.closes_at,
                state=suggestion.state,
                title=suggestion.title,
                caption=suggestion.caption,
                chosen=medium(suggestion.chosen_medium_id),
                ranking=[
                    m for m in (medium(i) for i in suggestion.ranking) if m is not None
                ],
                why=suggestion.why,
                attempts=suggestion.attempts,
                last_error=suggestion.last_error,
            )
        )
    return found
