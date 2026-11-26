"""TikTok as a Channel (spec #145): Login Kit for the account's tokens and the
Content Posting API (Direct Post) for videos.

The access token lives 24 hours, the refresh token a year; both come from
TikTok's OAuth endpoint (`/v2/oauth/token/`), first for the code the Superuser
pastes after logging in on TikTok, then for every refresh."""

import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Protocol
from urllib.parse import urlencode

import httpx

from pmp_backend.services.instagram import ChannelError
from pmp_backend.settings import Settings

TIMEOUT_SECONDS = 60
SCOPES = "user.info.basic,video.upload,video.publish"
# Who can see a post, as TikTok names it; creator info says which the account
# may use (only SELF_ONLY until the app passed TikTok's audit).
PRIVACY_LEVELS = {
    "PUBLIC_TO_EVERYONE": "Everyone",
    "MUTUAL_FOLLOW_FRIENDS": "Friends",
    "FOLLOWER_OF_CREATOR": "Followers",
    "SELF_ONLY": "Only me",
}
# A video goes up in one piece up to this size, otherwise in 10 MB pieces
# (TikTok: 5-64 MB per piece, the last one takes the rest).
SINGLE_UPLOAD_BYTES = 64 * 1000 * 1000
CHUNK_BYTES = 10 * 1000 * 1000
# How long TikTok may take to process an uploaded video.
PROCESSING_SECONDS = 300
POLL_SECONDS = 5
# TikTok's error codes that need a person, with what to do.
KNOWN_ERRORS = {
    "unaudited_client_can_only_post_to_private_accounts": (
        "Until TikTok's audit, the app can only post to a private account: set "
        "the TikTok account to Private (TikTok app, Settings and privacy, "
        "Privacy, Private account)."
    ),
    "spam_risk_too_many_posts": "TikTok's daily post limit for the account is reached.",
}


class CodeRefusedError(ChannelError):
    """TikTok refused the pasted code (wrong, used or expired)."""


@dataclass(frozen=True)
class Tokens:
    access_token: str
    expires_at: datetime
    refresh_token: str
    refresh_expires_at: datetime


@dataclass(frozen=True)
class CreatorInfo:
    """What TikTok allows this account to post (asked before every post)."""

    nickname: str
    privacy_levels: list[str]
    comment_disabled: bool
    duet_disabled: bool
    stitch_disabled: bool
    max_video_seconds: int


@dataclass(frozen=True)
class VideoPost:
    caption: str
    privacy_level: str
    allow_comment: bool
    allow_duet: bool
    allow_stitch: bool


class TikTok(Protocol):
    def exchange_code(self, code: str, now: datetime) -> Tokens:
        """The tokens for a Login Kit code; CodeRefusedError when TikTok
        refuses it, ChannelError when TikTok can't be reached."""
        ...

    def refresh(self, refresh_token: str, now: datetime) -> Tokens:
        """New tokens; ChannelError on failure."""
        ...

    def account_name(self, access_token: str) -> str:
        """The account's display name; ChannelError on failure."""
        ...

    def creator_info(self, access_token: str) -> CreatorInfo:
        """What the account may post; ChannelError on failure."""
        ...

    def publish_video(self, access_token: str, video: Path, post: VideoPost) -> str:
        """Post the video file (Direct Post) and wait until TikTok is done; the
        post's address when TikTok gives one (only public posts), else "".
        ChannelError on failure."""
        ...

    def send_photos_to_inbox(
        self, access_token: str, photo_urls: list[str], title: str, caption: str
    ) -> str:
        """Send a photo post to the account's TikTok inbox (upload mode, #150):
        TikTok downloads the photos from the links; a person picks the song and
        posts it in the app. Waits until it is in the inbox; the publish id.
        ChannelError on failure."""
        ...


def is_configured(settings: Settings) -> bool:
    return bool(
        settings.tiktok_client_key
        and settings.tiktok_client_secret
        and settings.tiktok_client_secret.get_secret_value()
    )


def authorize_url(settings: Settings, state: str) -> str:
    """TikTok's login page for the app, which sends the Superuser back to the
    redirect URI with `code` and `state` in the address."""
    query = urlencode(
        {
            "client_key": settings.tiktok_client_key,
            "scope": SCOPES,
            "response_type": "code",
            "redirect_uri": settings.tiktok_redirect_uri,
            "state": state,
        }
    )
    return f"{settings.tiktok_auth_url}?{query}"


def _reason(response: httpx.Response) -> str:
    try:
        answer = response.json()
    except ValueError:
        return f"TikTok answered {response.status_code}: {response.text[:200]}"
    error = answer.get("error")
    if isinstance(error, dict):
        message = error.get("message") or error.get("code")
    else:
        message = answer.get("error_description") or error
    return f"TikTok answered {response.status_code}: {message}"


def _tokens(answer: dict, now: datetime) -> Tokens:
    try:
        return Tokens(
            access_token=answer["access_token"],
            expires_at=now + timedelta(seconds=int(answer["expires_in"])),
            refresh_token=answer["refresh_token"],
            refresh_expires_at=now
            + timedelta(seconds=int(answer["refresh_expires_in"])),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ChannelError("TikTok gave no tokens.") from error


class HttpTikTok:
    """TikTok's API (TIKTOK_API_URL) for the app TIKTOK_CLIENT_KEY."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = httpx.Client(
            base_url=settings.tiktok_api_url, timeout=TIMEOUT_SECONDS
        )

    def _oauth(self, fields: dict[str, str], now: datetime) -> Tokens:
        secret = self._settings.tiktok_client_secret
        form = {
            "client_key": self._settings.tiktok_client_key or "",
            "client_secret": secret.get_secret_value() if secret else "",
        } | fields
        try:
            response = self._client.post("/v2/oauth/token/", data=form)
        except httpx.HTTPError as error:
            raise ChannelError(f"TikTok can't be reached: {error}") from error
        try:
            answer = response.json()
        except ValueError:
            answer = {}
        # TikTok answers a refused code with 200 and an "error" field.
        if response.status_code >= 400 or "error" in answer:
            if fields.get("grant_type") == "authorization_code":
                raise CodeRefusedError(_reason(response))
            raise ChannelError(_reason(response))
        return _tokens(answer, now)

    def exchange_code(self, code: str, now: datetime) -> Tokens:
        return self._oauth(
            {
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": self._settings.tiktok_redirect_uri,
            },
            now,
        )

    def refresh(self, refresh_token: str, now: datetime) -> Tokens:
        return self._oauth(
            {"grant_type": "refresh_token", "refresh_token": refresh_token}, now
        )

    def account_name(self, access_token: str) -> str:
        try:
            response = self._client.get(
                "/v2/user/info/",
                params={"fields": "open_id,display_name"},
                headers={"Authorization": f"Bearer {access_token}"},
            )
        except httpx.HTTPError as error:
            raise ChannelError(f"TikTok can't be reached: {error}") from error
        if response.status_code >= 400:
            raise ChannelError(_reason(response))
        try:
            return response.json()["data"]["user"]["display_name"]
        except (KeyError, TypeError, ValueError) as error:
            raise ChannelError("TikTok gave no account name.") from error

    def _post(self, url: str, access_token: str, body: dict) -> dict:
        """A Content Posting API call; its `data`. TikTok answers every call
        with an `error` whose code is "ok" when it worked."""
        try:
            response = self._client.post(
                url,
                json=body,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json; charset=UTF-8",
                },
            )
        except httpx.HTTPError as error:
            raise ChannelError(f"TikTok can't be reached: {error}") from error
        try:
            answer = response.json()
        except ValueError:
            answer = {}
        code = (answer.get("error") or {}).get("code", "ok")
        if response.status_code >= 400 or code != "ok":
            if code in KNOWN_ERRORS:
                raise ChannelError(KNOWN_ERRORS[code])
            message = (answer.get("error") or {}).get("message") or response.text[:200]
            raise ChannelError(
                f"TikTok answered {response.status_code} ({code}): {message}"
            )
        return answer.get("data") or {}

    def creator_info(self, access_token: str) -> CreatorInfo:
        data = self._post("/v2/post/publish/creator_info/query/", access_token, {})
        try:
            return CreatorInfo(
                nickname=data.get("creator_nickname") or data["creator_username"],
                privacy_levels=list(data["privacy_level_options"]),
                comment_disabled=bool(data.get("comment_disabled")),
                duet_disabled=bool(data.get("duet_disabled")),
                stitch_disabled=bool(data.get("stitch_disabled")),
                max_video_seconds=int(data.get("max_video_post_duration_sec") or 0),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ChannelError("TikTok gave no creator info.") from error

    def publish_video(self, access_token: str, video: Path, post: VideoPost) -> str:
        size = video.stat().st_size
        if size <= SINGLE_UPLOAD_BYTES:
            chunk, count = size, 1
        else:
            chunk, count = CHUNK_BYTES, size // CHUNK_BYTES
        started = self._post(
            "/v2/post/publish/video/init/",
            access_token,
            {
                "post_info": {
                    "title": post.caption,
                    "privacy_level": post.privacy_level,
                    "disable_comment": not post.allow_comment,
                    "disable_duet": not post.allow_duet,
                    "disable_stitch": not post.allow_stitch,
                },
                "source_info": {
                    "source": "FILE_UPLOAD",
                    "video_size": size,
                    "chunk_size": chunk,
                    "total_chunk_count": count,
                },
            },
        )
        try:
            publish_id, upload_url = started["publish_id"], started["upload_url"]
        except KeyError as error:
            raise ChannelError("TikTok gave no upload address.") from error
        with video.open("rb") as file:
            for number in range(count):
                start = number * chunk
                # The last piece takes the rest of the file.
                end = size - 1 if number == count - 1 else start + chunk - 1
                file.seek(start)
                piece = file.read(end - start + 1)
                try:
                    uploaded = httpx.put(
                        upload_url,
                        content=piece,
                        headers={
                            "Content-Type": "video/mp4",
                            "Content-Range": f"bytes {start}-{end}/{size}",
                        },
                        timeout=PROCESSING_SECONDS,
                    )
                except httpx.HTTPError as error:
                    raise ChannelError(f"The video upload failed: {error}") from error
                if uploaded.status_code >= 400:
                    raise ChannelError(
                        f"The video upload failed: {uploaded.status_code} "
                        f"{uploaded.text[:200]}"
                    )
        return self._wait_until_posted(access_token, publish_id)

    def send_photos_to_inbox(
        self, access_token: str, photo_urls: list[str], title: str, caption: str
    ) -> str:
        started = self._post(
            "/v2/post/publish/content/init/",
            access_token,
            {
                "post_info": {
                    "title": title,
                    "description": caption,
                    "auto_add_music": True,
                },
                "source_info": {
                    "source": "PULL_FROM_URL",
                    "photo_cover_index": 0,
                    "photo_images": photo_urls,
                },
                "post_mode": "MEDIA_UPLOAD",
                "media_type": "PHOTO",
            },
        )
        try:
            publish_id = started["publish_id"]
        except KeyError as error:
            raise ChannelError("TikTok gave no publish id.") from error
        self._wait_until_posted(access_token, publish_id, inbox=True)
        return publish_id

    def _wait_until_posted(
        self, access_token: str, publish_id: str, *, inbox: bool = False
    ) -> str:
        deadline = time.monotonic() + PROCESSING_SECONDS
        while True:
            data = self._post(
                "/v2/post/publish/status/fetch/",
                access_token,
                {"publish_id": publish_id},
            )
            status = data.get("status")
            if inbox and status == "SEND_TO_USER_INBOX":
                return ""
            if status == "PUBLISH_COMPLETE":
                ids = data.get("publicaly_available_post_id") or []
                return f"https://www.tiktok.com/video/{ids[0]}" if ids else ""
            if status == "FAILED":
                raise ChannelError(
                    f"TikTok couldn't post the video ({data.get('fail_reason')})."
                )
            if time.monotonic() > deadline:
                raise ChannelError("TikTok took too long to process the video.")
            time.sleep(POLL_SECONDS)
