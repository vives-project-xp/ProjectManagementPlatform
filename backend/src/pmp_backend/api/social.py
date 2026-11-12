from datetime import datetime, time
from typing import Annotated

from fastapi import APIRouter, File, Form, Response, UploadFile
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
from pmp_backend.services import social
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
    # "photo" (or, from #113, "video"); the file is GET /api/weekly-media/{id}.
    kind: str
    width: int
    height: int
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
    medium, data = social.read_medium(
        session, settings.social_media_dir, user, medium_id
    )
    media_type = "image/jpeg" if medium.kind == "photo" else "video/mp4"
    return Response(
        content=data,
        media_type=media_type,
        headers={"X-Content-Type-Options": "nosniff"},
    )
