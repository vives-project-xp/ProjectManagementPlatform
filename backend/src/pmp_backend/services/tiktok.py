"""TikTok as a Channel (spec #145): Login Kit for the account's tokens and,
later, the Content Posting API.

The access token lives 24 hours, the refresh token a year; both come from
TikTok's OAuth endpoint (`/v2/oauth/token/`), first for the code the Superuser
pastes after logging in on TikTok, then for every refresh."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol
from urllib.parse import urlencode

import httpx

from pmp_backend.services.instagram import ChannelError
from pmp_backend.settings import Settings

TIMEOUT_SECONDS = 60
SCOPES = "user.info.basic,video.upload,video.publish"


class CodeRefusedError(ChannelError):
    """TikTok refused the pasted code (wrong, used or expired)."""


@dataclass(frozen=True)
class Tokens:
    access_token: str
    expires_at: datetime
    refresh_token: str
    refresh_expires_at: datetime


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
