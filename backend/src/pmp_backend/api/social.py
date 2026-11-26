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
    ClientDep,
    CurrentUserDep,
    SessionDep,
    SettingsDep,
    StudentDep,
    SuperuserDep,
    TeacherOrSuperuserDep,
)
from pmp_backend.api.schemas import ProjectRefOut
from pmp_backend.models import WeeklySlideshow
from pmp_backend.services import (
    clients,
    post_ai,
    posting,
    publishing,
    slideshows,
    social,
    suggestions,
    tiktok,
    tiktok_connection,
    tiktok_posts,
)
from pmp_backend.services.instagram import ChannelError
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
    # TikTok (spec #145): the videos' Posting times, the Weekly slideshow's
    # Posting time and its cut-off.
    tiktok_weekdays: list[int]
    tiktok_times: list[str]
    slideshow_weekday: int
    slideshow_time: str
    slideshow_cutoff_weekday: int
    slideshow_cutoff_time: str

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
            tiktok_weekdays=settings.tiktok_weekdays,
            tiktok_times=settings.tiktok_times,
            slideshow_weekday=settings.slideshow_weekday,
            slideshow_time=settings.slideshow_time.strftime("%H:%M"),
            slideshow_cutoff_weekday=settings.slideshow_cutoff_weekday,
            slideshow_cutoff_time=settings.slideshow_cutoff_time.strftime("%H:%M"),
        )


class SocialSettingsIn(BaseModel):
    upload_weekday: Weekday | None
    upload_time: ClockTime | None
    instagram_weekdays: list[Weekday]
    instagram_times: list[ClockTime]
    fixed_hashtags: str
    # Left out: kept as they are.
    tiktok_weekdays: list[Weekday] | None = None
    tiktok_times: list[ClockTime] | None = None
    slideshow_weekday: Weekday | None = None
    slideshow_time: ClockTime | None = None
    slideshow_cutoff_weekday: Weekday | None = None
    slideshow_cutoff_time: ClockTime | None = None


def _moment(weekday: int | None, at: str | None) -> tuple[int, time] | None:
    if weekday is None and at is None:
        return None
    if weekday is None or at is None:
        raise social.SocialError("Give the weekday and the time together.")
    return weekday, time.fromisoformat(at)


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
            tiktok_weekdays=body.tiktok_weekdays,
            tiktok_times=body.tiktok_times,
            slideshow=_moment(body.slideshow_weekday, body.slideshow_time),
            slideshow_cutoff=_moment(
                body.slideshow_cutoff_weekday, body.slideshow_cutoff_time
            ),
        )
    )


class TikTokStatusOut(BaseModel):
    # Whether TIKTOK_CLIENT_KEY and TIKTOK_CLIENT_SECRET are set.
    configured: bool
    # Whether the platform has a valid token for the account.
    connected: bool
    account_name: str | None
    connected_at: datetime | None
    # When the access token runs out (refreshed before then) and when the
    # refresh token does (then connect again).
    expires_at: datetime | None
    refresh_expires_at: datetime | None
    # Why the connection doesn't work (a failed refresh, an expired one).
    error: str | None
    # TikTok's login page, with a fresh `state`; null when not configured.
    connect_url: str | None


def _tiktok_status(session, settings, user_id: int) -> TikTokStatusOut:
    now = datetime.now(posting.BRUSSELS)
    found = tiktok_connection.status(session, settings, now)
    session.commit()
    url = None
    if found.configured:
        url = tiktok.authorize_url(
            settings, tiktok_connection.make_state(settings, user_id, now)
        )
    return TikTokStatusOut(
        configured=found.configured,
        connected=found.connected,
        account_name=found.account_name,
        connected_at=found.connected_at,
        expires_at=found.expires_at,
        refresh_expires_at=found.refresh_expires_at,
        error=found.error,
        connect_url=url,
    )


@router.get("/social/tiktok")
def get_tiktok(
    session: SessionDep, settings: SettingsDep, user: SuperuserDep
) -> TikTokStatusOut:
    return _tiktok_status(session, settings, user.id)


class TikTokConnectIn(BaseModel):
    # The address TikTok sent the Superuser to (or just its code).
    pasted: Annotated[str, StringConstraints(max_length=4000)]


@router.post("/social/tiktok/connect")
def connect_tiktok(
    body: TikTokConnectIn,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    user: SuperuserDep,
) -> TikTokStatusOut:
    tiktok_connection.connect(
        session,
        request.app.state.tiktok,
        settings,
        user.id,
        body.pasted,
        datetime.now(posting.BRUSSELS),
    )
    return _tiktok_status(session, settings, user.id)


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
    # The Post suggestion's state once there is one (e.g. "refused"), and why.
    suggestion_state: str | None
    refusal_reason: str | None
    # Its Posting time once Posted; when it was posted by hand or published.
    scheduled_for: datetime | None
    posted_at: datetime | None
    # The post on Instagram once published automatically (#117).
    published_url: str | None
    # Set once the never-posted Media were deleted, 4 months after the week.
    media_removed_at: datetime | None
    # Its video on TikTok (#147): "scheduled", "published", "to_post_by_hand"
    # or "posted_by_hand"; null when it isn't on TikTok.
    tiktok_state: str | None
    tiktok_scheduled_for: datetime | None
    tiktok_posted_at: datetime | None
    # The Posting time of the Weekly slideshow with one of its photos (#150).
    slideshow_at: datetime | None

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


class ClientWeekOut(BaseModel):
    """A Weekly update as a Client sees it (#135): the team's text and Media,
    never the Post suggestion or its outcome."""

    closes_at: datetime
    text: str
    edited_by: str | None
    edited_at: datetime | None
    is_open: bool
    media: list[MediumOut]


@router.get("/my-projects/{project_id}/weekly-updates")
def followed_weekly_updates(
    project_id: int, session: SessionDep, client: ClientDep
) -> list[ClientWeekOut]:
    """Every Weekly update of a followed Project, the open week included,
    newest first."""
    project = clients.followed_project(session, client, project_id)
    return [
        ClientWeekOut(
            closes_at=week.closes_at,
            text=week.text,
            edited_by=week.edited_by,
            edited_at=week.edited_at,
            is_open=week.is_open,
            media=[MediumOut(**vars(medium)) for medium in week.media],
        )
        for week in social.weekly_updates(session, project.id)
    ]


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
    # Who last edited, refused or regenerated it (null before any Review).
    reviewed_by: str | None
    reviewed_at: datetime | None
    refusal_reason: str | None
    # Its Posting time once Posted ("scheduled"); who posted it by hand, when
    # (or when it was published automatically).
    scheduled_for: datetime | None
    posted_by: str | None
    posted_at: datetime | None
    # Automatic publishing (#117): why the last try failed (on To post today
    # when it gave up), and the post on Instagram once "published".
    publish_error: str | None
    published_url: str | None
    # Whether the Weekly update has a ready video (Also on TikTok, #147), and
    # its TikTok post once there is one.
    has_video: bool
    tiktok: "TikTokPostOut | None"


class TikTokPostOut(BaseModel):
    # "scheduled", "published", "to_post_by_hand" or "posted_by_hand".
    state: str
    scheduled_for: datetime | None
    # Who can see it (TikTok's name, e.g. "SELF_ONLY") and the reviewer's
    # other choices.
    privacy_level: str
    allow_comment: bool
    allow_duet: bool
    allow_stitch: bool
    # Why the last try failed (on To post today when it gave up).
    error: str | None
    # The video file (GET /api/weekly-media/{id}); null once it was deleted.
    medium_id: int | None
    posted_by: str | None
    posted_at: datetime | None
    published_url: str | None


SuggestionOut.model_rebuild()


def _tiktok_out(post) -> TikTokPostOut | None:
    if post is None:
        return None
    return TikTokPostOut(
        state=post.state,
        scheduled_for=post.scheduled_for,
        privacy_level=post.privacy_level,
        allow_comment=post.allow_comment,
        allow_duet=post.allow_duet,
        allow_stitch=post.allow_stitch,
        error=post.error,
        medium_id=post.medium_id,
        posted_by=(post.posted_by.full_name if post.posted_by else "Deleted user")
        if post.state == "posted_by_hand"
        else None,
        posted_at=post.posted_at,
        published_url=post.published_url,
    )


@router.get("/post-suggestions")
def list_suggestions(
    session: SessionDep, user: TeacherOrSuperuserDep, mine: bool = False
) -> list[SuggestionOut]:
    """`mine`: only of Projects the User is the Product Owner of."""
    return _suggestions_out(
        suggestions.suggestions(session, owner_id=user.id if mine else None)
    )


def _suggestions_out(views: list[suggestions.SuggestionView]) -> list[SuggestionOut]:
    found = []
    for view in views:
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
                reviewed_by=(
                    suggestion.reviewed_by.full_name
                    if suggestion.reviewed_by
                    else "Deleted user"
                )
                if suggestion.reviewed_at
                else None,
                reviewed_at=suggestion.reviewed_at,
                refusal_reason=suggestion.refusal_reason,
                scheduled_for=suggestion.scheduled_for,
                # Published automatically: nobody posted it by hand.
                posted_by=(
                    suggestion.posted_by.full_name
                    if suggestion.posted_by
                    else "Deleted user"
                )
                if suggestion.state == "posted_by_hand"
                else None,
                posted_at=suggestion.posted_at,
                publish_error=suggestion.publish_error,
                published_url=suggestion.published_url,
                has_video=tiktok_posts.video_of(suggestion) is not None,
                tiktok=_tiktok_out(suggestion.tiktok_post),
            )
        )
    return found


def _one(session, suggestion_id: int) -> SuggestionOut:
    views = [
        view
        for view in suggestions.suggestions(session)
        if view.suggestion.id == suggestion_id
    ]
    return _suggestions_out(views)[0]


class SuggestionIn(BaseModel):
    title: str
    caption: str
    chosen_medium_id: int


class RefusalIn(BaseModel):
    reason: str | None = None


@router.put("/post-suggestions/{suggestion_id}")
def edit_suggestion(
    suggestion_id: int,
    body: SuggestionIn,
    session: SessionDep,
    user: TeacherOrSuperuserDep,
) -> SuggestionOut:
    """Edit a suggestion waiting for Review, or write one the AI couldn't make."""
    suggestions.edit(
        session,
        user,
        suggestion_id,
        title=body.title,
        caption=body.caption,
        chosen_medium_id=body.chosen_medium_id,
    )
    return _one(session, suggestion_id)


@router.post("/post-suggestions/{suggestion_id}/refuse")
def refuse_suggestion(
    suggestion_id: int,
    body: RefusalIn,
    session: SessionDep,
    user: TeacherOrSuperuserDep,
) -> SuggestionOut:
    suggestions.refuse(session, user, suggestion_id, body.reason)
    return _one(session, suggestion_id)


@router.post("/post-suggestions/{suggestion_id}/generate")
def generate_again(
    suggestion_id: int,
    request: Request,
    background: BackgroundTasks,
    session: SessionDep,
    settings: SettingsDep,
    user: TeacherOrSuperuserDep,
) -> SuggestionOut:
    """The AI starts over; the answer comes in the background."""
    suggestions.generate_again(session, user, suggestion_id)
    background.add_task(
        suggestions.attempt_now,
        request.app.state.sessionmaker,
        request.app.state.llm,
        settings.social_media_dir,
        suggestion_id,
    )
    return _one(session, suggestion_id)


class PostIn(BaseModel):
    # Also on TikTok (#147): the video too, with who can see it (one of
    # TikTok's privacy levels) and the interaction switches.
    also_on_tiktok: bool = False
    privacy_level: str | None = None
    allow_comment: bool = True
    allow_duet: bool = False
    allow_stitch: bool = False


@router.post("/post-suggestions/{suggestion_id}/post")
def post_suggestion(
    suggestion_id: int,
    session: SessionDep,
    user: TeacherOrSuperuserDep,
    body: PostIn | None = None,
) -> SuggestionOut:
    """Accept it: it gets Instagram's next free Posting time (no "right now"),
    and its video TikTok's when Also on TikTok is ticked."""
    choice = None
    if body is not None and body.also_on_tiktok:
        choice = tiktok_posts.Choice(
            privacy_level=body.privacy_level or "",
            allow_comment=body.allow_comment,
            allow_duet=body.allow_duet,
            allow_stitch=body.allow_stitch,
        )
    posting.post(session, user, suggestion_id, tiktok=choice)
    return _one(session, suggestion_id)


@router.post("/post-suggestions/{suggestion_id}/tiktok/pull-back")
def pull_back_tiktok(
    suggestion_id: int, session: SessionDep, user: TeacherOrSuperuserDep
) -> SuggestionOut:
    """Take the video out of TikTok's line; the Instagram post stays."""
    tiktok_posts.pull_back(session, suggestion_id)
    return _one(session, suggestion_id)


@router.post("/post-suggestions/{suggestion_id}/tiktok/posted")
def mark_tiktok_posted(
    suggestion_id: int, session: SessionDep, user: TeacherOrSuperuserDep
) -> SuggestionOut:
    """The video was posted on TikTok by hand from To post today."""
    tiktok_posts.mark_posted(session, user, suggestion_id)
    return _one(session, suggestion_id)


class CreatorInfoOut(BaseModel):
    # Whether the TikTok account is connected; without it the options are
    # TikTok's usual ones and the post goes to To post today.
    connected: bool
    nickname: str | None
    # Who can see a post: TikTok's name and how it is shown.
    privacy_levels: dict[str, str]
    comment_disabled: bool
    duet_disabled: bool
    stitch_disabled: bool
    # Why the account's options couldn't be fetched.
    error: str | None


@router.get("/social/tiktok/creator-info")
def creator_info(
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    user: TeacherOrSuperuserDep,
) -> CreatorInfoOut:
    """What the account may post, for the Also on TikTok choices in Review."""
    now = datetime.now(posting.BRUSSELS)
    token = tiktok_connection.access_token(session, settings, now)
    session.commit()
    fallback = CreatorInfoOut(
        connected=False,
        nickname=None,
        privacy_levels=dict(tiktok.PRIVACY_LEVELS),
        comment_disabled=False,
        duet_disabled=False,
        stitch_disabled=False,
        error=None,
    )
    if token is None:
        return fallback
    try:
        info = request.app.state.tiktok.creator_info(token)
    except ChannelError as error:
        return fallback.model_copy(update={"error": str(error)})
    return CreatorInfoOut(
        connected=True,
        nickname=info.nickname,
        privacy_levels={
            level: tiktok.PRIVACY_LEVELS.get(level, level)
            for level in info.privacy_levels
        },
        comment_disabled=info.comment_disabled,
        duet_disabled=info.duet_disabled,
        stitch_disabled=info.stitch_disabled,
        error=None,
    )


@router.post("/post-suggestions/{suggestion_id}/pull-back")
def pull_back(
    suggestion_id: int, session: SessionDep, user: TeacherOrSuperuserDep
) -> SuggestionOut:
    """Take a Scheduled post out of the line, back to Review."""
    posting.pull_back(session, user, suggestion_id)
    return _one(session, suggestion_id)


@router.post("/post-suggestions/{suggestion_id}/posted")
def mark_posted(
    suggestion_id: int, session: SessionDep, user: TeacherOrSuperuserDep
) -> SuggestionOut:
    """It was published by hand from the To post today list."""
    posting.mark_posted(session, user, suggestion_id)
    return _one(session, suggestion_id)


# The Weekly slideshow (#149)


class SlideshowPhotoOut(BaseModel):
    project: ProjectRefOut
    medium: MediumOut


class SlideshowProjectOut(BaseModel):
    project: ProjectRefOut
    # Its photos, best first (the one on Instagram last), to swap with.
    photos: list[MediumOut]


class SlideshowOut(BaseModel):
    id: int
    # The Upload week it shows.
    closes_at: datetime
    # "generating", "waiting" (for Review), "failed" (write it yourself),
    # "refused", or "none" (no Posted Project had a photo).
    state: str
    title: str | None
    caption: str | None
    attempts: int
    last_error: str | None
    reviewed_by: str | None
    reviewed_at: datetime | None
    refusal_reason: str | None
    # Posting (#150): its Posting time once Posted; why sending failed (or
    # "Not posted in time" when dropped); who marked it posted, and when.
    scheduled_for: datetime | None
    publish_error: str | None
    posted_by: str | None
    posted_at: datetime | None
    # In order.
    photos: list[SlideshowPhotoOut]
    # The week's Posted Projects with photos.
    projects: list[SlideshowProjectOut]


def _slideshow_out(view: slideshows.SlideshowView) -> SlideshowOut:
    slideshow = view.slideshow

    def ref(project) -> ProjectRefOut:
        return ProjectRefOut(id=project.id, title=project.title)

    return SlideshowOut(
        id=slideshow.id,
        closes_at=slideshow.closes_at,
        state=slideshow.state,
        title=slideshow.title,
        caption=slideshow.caption,
        attempts=slideshow.attempts,
        last_error=slideshow.last_error,
        reviewed_by=(
            slideshow.reviewed_by.full_name if slideshow.reviewed_by else "Deleted user"
        )
        if slideshow.reviewed_at
        else None,
        reviewed_at=slideshow.reviewed_at,
        refusal_reason=slideshow.refusal_reason,
        scheduled_for=slideshow.scheduled_for,
        publish_error=slideshow.publish_error,
        posted_by=(
            slideshow.posted_by.full_name if slideshow.posted_by else "Deleted user"
        )
        if slideshow.state == "posted"
        else None,
        posted_at=slideshow.posted_at,
        photos=[
            SlideshowPhotoOut(
                project=ref(p.project), medium=MediumOut(**vars(p.medium))
            )
            for p in view.photos
        ],
        projects=[
            SlideshowProjectOut(
                project=ref(p.project),
                photos=[MediumOut(**vars(m)) for m in p.photos],
            )
            for p in view.projects
        ],
    )


def _latest_slideshow(session) -> SlideshowOut | None:
    view = slideshows.latest(session)
    session.commit()
    return _slideshow_out(view) if view else None


@router.get("/slideshows/latest")
def latest_slideshow(
    session: SessionDep, user: TeacherOrSuperuserDep
) -> SlideshowOut | None:
    """The newest Weekly slideshow, or null before the first cut-off."""
    return _latest_slideshow(session)


class SlideshowTextIn(BaseModel):
    title: str
    caption: str


@router.put("/slideshows/{slideshow_id}")
def edit_slideshow(
    slideshow_id: int,
    body: SlideshowTextIn,
    session: SessionDep,
    user: TeacherOrSuperuserDep,
) -> SlideshowOut | None:
    """Edit the text, or write it yourself when the AI couldn't."""
    slideshows.edit(session, user, slideshow_id, title=body.title, caption=body.caption)
    return _latest_slideshow(session)


class SlideshowPhotosIn(BaseModel):
    # The photos in their new order (swap, remove and reorder in one).
    medium_ids: list[int]


@router.put("/slideshows/{slideshow_id}/photos")
def set_slideshow_photos(
    slideshow_id: int,
    body: SlideshowPhotosIn,
    session: SessionDep,
    user: TeacherOrSuperuserDep,
) -> SlideshowOut | None:
    slideshows.set_photos(session, user, slideshow_id, body.medium_ids)
    return _latest_slideshow(session)


@router.post("/slideshows/{slideshow_id}/generate")
def generate_slideshow_again(
    slideshow_id: int,
    request: Request,
    background: BackgroundTasks,
    session: SessionDep,
    user: TeacherOrSuperuserDep,
) -> SlideshowOut | None:
    """Put it together again (with Projects Posted since) and let the AI write
    it again; the answer comes in the background."""
    slideshows.generate_again(session, user, slideshow_id)
    make_session, llm = request.app.state.sessionmaker, request.app.state.llm

    def write() -> None:
        with make_session() as fresh:
            slideshows.attempt(fresh, llm, slideshow_id, datetime.now(posting.BRUSSELS))

    background.add_task(write)
    return _latest_slideshow(session)


@router.post("/slideshows/{slideshow_id}/post")
def post_slideshow(
    slideshow_id: int, session: SessionDep, user: TeacherOrSuperuserDep
) -> SlideshowOut:
    """Accept it: it waits for its Posting time, or goes out within a minute
    when that has passed (#150)."""
    slideshows.post(session, user, slideshow_id)
    return _slideshow_out(_view(session, slideshow_id))


@router.post("/slideshows/{slideshow_id}/pull-back")
def pull_back_slideshow(
    slideshow_id: int, session: SessionDep, user: TeacherOrSuperuserDep
) -> SlideshowOut:
    slideshows.pull_back(session, user, slideshow_id)
    return _slideshow_out(_view(session, slideshow_id))


class SongCheckIn(BaseModel):
    # "I listened to the song and posted it in the TikTok app."
    song_checked: bool = False


@router.post("/slideshows/{slideshow_id}/posted")
def mark_slideshow_posted(
    slideshow_id: int,
    body: SongCheckIn,
    session: SessionDep,
    user: TeacherOrSuperuserDep,
) -> SlideshowOut:
    """Posted in the TikTok app, after the Song check."""
    slideshows.mark_posted(session, user, slideshow_id, body.song_checked)
    return _slideshow_out(_view(session, slideshow_id))


@router.get("/slideshows/{slideshow_id}/photos.zip")
def slideshow_photos_zip(
    slideshow_id: int,
    session: SessionDep,
    settings: SettingsDep,
    user: TeacherOrSuperuserDep,
) -> Response:
    """The photos in order (01-<project>.jpg …), to post by hand."""
    name, data = slideshows.photos_zip(session, settings.social_media_dir, slideshow_id)
    return Response(
        data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


class SlideshowListsOut(BaseModel):
    # In the TikTok inbox or to post by hand; Scheduled; lately posted.
    to_finish: list[SlideshowOut]
    scheduled: list[SlideshowOut]
    posted: list[SlideshowOut]


@router.get("/slideshows")
def slideshow_lists(
    session: SessionDep, user: TeacherOrSuperuserDep
) -> SlideshowListsOut:
    found = slideshows.lists(session)
    session.commit()
    return SlideshowListsOut(
        to_finish=[_slideshow_out(v) for v in found.to_finish],
        scheduled=[_slideshow_out(v) for v in found.scheduled],
        posted=[_slideshow_out(v) for v in found.posted],
    )


def _view(session, slideshow_id: int) -> slideshows.SlideshowView:
    slideshow = session.get(WeeklySlideshow, slideshow_id, populate_existing=True)
    view = slideshows.view_of(session, slideshow)
    session.commit()
    return view


@router.post("/slideshows/{slideshow_id}/refuse")
def refuse_slideshow(
    slideshow_id: int,
    body: RefusalIn,
    session: SessionDep,
    user: TeacherOrSuperuserDep,
) -> SlideshowOut | None:
    """No slideshow this week."""
    slideshows.refuse(session, user, slideshow_id, body.reason)
    return _latest_slideshow(session)


class ChannelOut(BaseModel):
    # Automatic publishing on Instagram (#117); never the token itself.
    automatic: bool
    # Photo posts need the site reachable from the internet (PUBLIC_MEDIA_URL).
    photos_automatic: bool
    expires_at: datetime | None
    # Why the last token refresh failed; null after a successful one.
    refresh_error: str | None


class ScheduledPostsOut(BaseModel):
    # Due posts to publish by hand (oldest first), and the line (soonest first).
    to_post: list[SuggestionOut]
    scheduled: list[SuggestionOut]
    # The last posts published automatically, newest first (#117).
    published: list[SuggestionOut]
    channel: ChannelOut
    # TikTok videos (#147), the same three lists for the suggestions' TikTok
    # posts, and whether they are published automatically.
    tiktok_to_post: list[SuggestionOut]
    tiktok_scheduled: list[SuggestionOut]
    tiktok_published: list[SuggestionOut]
    tiktok_automatic: bool
    tiktok_error: str | None


@router.get("/scheduled-posts")
def scheduled_posts(
    session: SessionDep, settings: SettingsDep, user: TeacherOrSuperuserDep
) -> ScheduledPostsOut:
    to_post, scheduled = posting.lists(session)
    published = posting.recently_published(session)
    by_id = {
        found.id: found for found in _suggestions_out(suggestions.suggestions(session))
    }
    tiktok_to_post, tiktok_scheduled, tiktok_published = tiktok_posts.lists(session)
    connection = tiktok_connection.status(
        session, settings, datetime.now(posting.BRUSSELS)
    )
    session.commit()
    return ScheduledPostsOut(
        to_post=[by_id[i] for i in to_post],
        scheduled=[by_id[i] for i in scheduled],
        published=[by_id[i] for i in published],
        channel=ChannelOut(**vars(publishing.status(session, settings))),
        tiktok_to_post=[by_id[i] for i in tiktok_to_post],
        tiktok_scheduled=[by_id[i] for i in tiktok_scheduled],
        tiktok_published=[by_id[i] for i in tiktok_published],
        tiktok_automatic=connection.connected,
        tiktok_error=connection.error,
    )
