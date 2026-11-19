"""Instagram as a Channel (spec #110, #117): the Instagram API with Instagram
Login, for the team's Instagram Business account.

A photo post: Instagram downloads the photo from a Publish link (ADR 0010). A
Reel: the video is uploaded directly (resumable upload), so it works before the
VM is reachable from the internet. Both: create a media container, wait until
Instagram has processed it, publish it, then ask for its permalink."""

import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Protocol

import httpx

from pmp_backend.settings import Settings

TIMEOUT_SECONDS = 60
# How long Instagram may take to process a container (a Reel takes longest).
PROCESSING_SECONDS = 300
POLL_SECONDS = 5


class ChannelError(Exception):
    """Publishing or refreshing failed; the text says why, for the notice."""


@dataclass(frozen=True)
class Published:
    media_id: str
    url: str


@dataclass(frozen=True)
class RefreshedToken:
    token: str
    expires_at: datetime


class Channel(Protocol):
    def publish_photo(self, token: str, image_url: str, caption: str) -> Published:
        """A photo post of the photo at `image_url`; ChannelError on failure."""
        ...

    def publish_reel(self, token: str, video: Path, caption: str) -> Published:
        """A Reel of the video file; ChannelError on failure."""
        ...

    def refresh(self, token: str, now: datetime) -> RefreshedToken:
        """A new long-lived token; ChannelError on failure."""
        ...


def is_configured(settings: Settings) -> bool:
    return bool(
        settings.instagram_token and settings.instagram_token.get_secret_value()
    )


def _reason(response: httpx.Response) -> str:
    try:
        message = response.json()["error"]["message"]
    except (ValueError, KeyError, TypeError):
        message = response.text[:200]
    return f"Instagram answered {response.status_code}: {message}"


class HttpInstagram:
    """Instagram's Graph API (INSTAGRAM_API_URL) for INSTAGRAM_ACCOUNT_ID."""

    def __init__(self, settings: Settings) -> None:
        self._account = settings.instagram_account_id
        self._refresh_url = settings.instagram_refresh_url
        self._client = httpx.Client(
            base_url=settings.instagram_api_url, timeout=TIMEOUT_SECONDS
        )

    def _send(self, method: str, url: str, token: str, **kwargs) -> dict:
        params = kwargs.pop("params", {}) | {"access_token": token}
        try:
            response = self._client.request(method, url, params=params, **kwargs)
        except httpx.HTTPError as error:
            raise ChannelError(f"Instagram can't be reached: {error}") from error
        if response.status_code >= 400:
            raise ChannelError(_reason(response))
        return response.json()

    def _wait_until_processed(self, token: str, container: str) -> None:
        deadline = time.monotonic() + PROCESSING_SECONDS
        while True:
            status = self._send(
                "GET", f"/{container}", token, params={"fields": "status_code"}
            ).get("status_code")
            if status == "FINISHED":
                return
            if status in ("ERROR", "EXPIRED"):
                raise ChannelError(f"Instagram couldn't process the media ({status}).")
            if time.monotonic() > deadline:
                raise ChannelError("Instagram took too long to process the media.")
            time.sleep(POLL_SECONDS)

    def _publish(self, token: str, container: str) -> Published:
        self._wait_until_processed(token, container)
        media_id = self._send(
            "POST",
            f"/{self._account}/media_publish",
            token,
            params={"creation_id": container},
        )["id"]
        permalink = self._send(
            "GET", f"/{media_id}", token, params={"fields": "permalink"}
        ).get("permalink", "")
        return Published(media_id=media_id, url=permalink)

    def publish_photo(self, token: str, image_url: str, caption: str) -> Published:
        container = self._send(
            "POST",
            f"/{self._account}/media",
            token,
            params={"image_url": image_url, "caption": caption},
        )["id"]
        return self._publish(token, container)

    def publish_reel(self, token: str, video: Path, caption: str) -> Published:
        created = self._send(
            "POST",
            f"/{self._account}/media",
            token,
            params={
                "media_type": "REELS",
                "upload_type": "resumable",
                "caption": caption,
            },
        )
        data = video.read_bytes()
        try:
            uploaded = httpx.post(
                created["uri"],
                headers={
                    "Authorization": f"OAuth {token}",
                    "offset": "0",
                    "file_size": str(len(data)),
                },
                content=data,
                timeout=PROCESSING_SECONDS,
            )
        except httpx.HTTPError as error:
            raise ChannelError(f"The video upload failed: {error}") from error
        if uploaded.status_code >= 400:
            raise ChannelError(_reason(uploaded))
        return self._publish(token, created["id"])

    def refresh(self, token: str, now: datetime) -> RefreshedToken:
        answer = self._send(
            "GET",
            self._refresh_url,
            token,
            params={"grant_type": "ig_refresh_token"},
        )
        try:
            return RefreshedToken(
                token=answer["access_token"],
                expires_at=now + timedelta(seconds=int(answer["expires_in"])),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ChannelError("Instagram gave no new token.") from error
