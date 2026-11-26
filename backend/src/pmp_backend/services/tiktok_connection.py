"""Connecting the TikTok account (spec #145, #146): the Superuser logs in on
TikTok, which sends them to the registered redirect URI (today the GitHub
repo) with a `code` in the address; they paste that address here. The tokens
are kept in `channel_tokens` (row "tiktok") and refreshed before the 24-hour
access token runs out, so about once a day."""

import hashlib
import hmac
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import parse_qs, unquote, urlsplit

from sqlalchemy.orm import Session

from pmp_backend.errors import Refused, Unavailable
from pmp_backend.models import ChannelToken
from pmp_backend.services import tiktok
from pmp_backend.services.instagram import ChannelError
from pmp_backend.services.tiktok import CodeRefusedError, TikTok
from pmp_backend.settings import Settings

log = logging.getLogger(__name__)

CHANNEL = "tiktok"
# How long a Connect TikTok link may be used.
STATE_LIFETIME = timedelta(minutes=30)
# The access token is refreshed when it runs out within this time.
REFRESH_BEFORE = timedelta(hours=2)
# A failed refresh is tried again after this.
REFRESH_RETRY = timedelta(minutes=30)
EXPIRED = "The TikTok connection has expired. Connect TikTok again."


class TikTokError(Refused):
    """Connecting was refused; the message is fit to show."""


class TikTokUnavailableError(TikTokError, Unavailable):
    pass


def _signature(settings: Settings, user_id: int, issued: int) -> str:
    message = f"tiktok-connect:{user_id}:{issued}".encode()
    digest = hmac.new(settings.jwt_secret.encode(), message, hashlib.sha256)
    return digest.hexdigest()[:32]


def make_state(settings: Settings, user_id: int, now: datetime) -> str:
    """A `state` for TikTok's login link, tied to this Superuser and time, so a
    pasted address is known to come from a link the platform made."""
    issued = int(now.timestamp())
    return f"{issued}.{_signature(settings, user_id, issued)}"


def _state_is_valid(
    settings: Settings, user_id: int, state: str, now: datetime
) -> bool:
    issued_text, _, signature = state.partition(".")
    try:
        issued = int(issued_text)
    except ValueError:
        return False
    if not hmac.compare_digest(signature, _signature(settings, user_id, issued)):
        return False
    age = now - datetime.fromtimestamp(issued, tz=now.tzinfo)
    return timedelta(0) <= age <= STATE_LIFETIME


def code_from(settings: Settings, user_id: int, pasted: str, now: datetime) -> str:
    """The code in a pasted address (whose `state` must be ours) or a pasted
    bare code."""
    text = pasted.strip()
    if not text:
        raise TikTokError("Paste the address TikTok sent you to.")
    if "code=" not in text and "error=" not in text:
        return unquote(text)
    query = parse_qs(urlsplit(text).query or text.partition("?")[2])
    if "error" in query:
        reason = query.get("error_description", query["error"])[0]
        raise TikTokError(f"TikTok didn't connect: {reason}")
    state = query.get("state", [""])[0]
    if not _state_is_valid(settings, user_id, state, now):
        raise TikTokError(
            "This address comes from an old or another Connect TikTok link. "
            "Click Connect TikTok again."
        )
    code = query.get("code", [""])[0]
    if not code:
        raise TikTokError("This address has no code. Click Connect TikTok again.")
    return code


def connect(
    session: Session,
    client: TikTok,
    settings: Settings,
    user_id: int,
    pasted: str,
    now: datetime,
) -> None:
    """Exchange the pasted code for the account's tokens and keep them."""
    if not tiktok.is_configured(settings):
        raise TikTokError(
            "TikTok isn't set up on the server (TIKTOK_CLIENT_KEY and "
            "TIKTOK_CLIENT_SECRET)."
        )
    code = code_from(settings, user_id, pasted, now)
    try:
        tokens = client.exchange_code(code, now)
        name = client.account_name(tokens.access_token)
    except CodeRefusedError as error:
        raise TikTokError(
            f"TikTok refused the code ({error}). Click Connect TikTok and try "
            "again: a code works only once and only for a few minutes."
        ) from error
    except ChannelError as error:
        raise TikTokUnavailableError(str(error)) from error
    row = session.get(ChannelToken, CHANNEL, with_for_update=True)
    if row is None:
        row = ChannelToken(channel=CHANNEL, token="")
        session.add(row)
    row.token = tokens.access_token
    row.expires_at = tokens.expires_at
    row.refresh_token = tokens.refresh_token
    row.refresh_expires_at = tokens.refresh_expires_at
    row.account_name = name[:200]
    row.connected_at = now
    row.refreshed_at = None
    row.refresh_error = None
    session.commit()


def refresh_due(
    session: Session, client: TikTok, settings: Settings, now: datetime
) -> bool:
    """Refresh the tokens when the access token runs out soon; a failure is
    kept for the notice and tried again later. Whether it was refreshed."""
    row = session.get(ChannelToken, CHANNEL, with_for_update=True)
    if (
        row is None
        or not tiktok.is_configured(settings)
        or not row.refresh_token
        or (row.expires_at is not None and row.expires_at - now > REFRESH_BEFORE)
        or (row.refreshed_at is not None and now - row.refreshed_at < REFRESH_RETRY)
    ):
        session.commit()
        return False
    row.refreshed_at = now
    if row.refresh_expires_at is not None and row.refresh_expires_at <= now:
        row.refresh_error = EXPIRED
        session.commit()
        return False
    try:
        tokens = client.refresh(row.refresh_token, now)
    except ChannelError as error:
        row.refresh_error = str(error)[:500]
        session.commit()
        log.warning("Refreshing the TikTok token failed: %s", error)
        return False
    row.token = tokens.access_token
    row.expires_at = tokens.expires_at
    row.refresh_token = tokens.refresh_token
    row.refresh_expires_at = tokens.refresh_expires_at
    row.refresh_error = None
    session.commit()
    return True


def access_token(session: Session, settings: Settings, now: datetime) -> str | None:
    """The account's valid access token, or None (TikTok posts then go to To
    post today)."""
    row = session.get(ChannelToken, CHANNEL)
    if (
        row is None
        or not tiktok.is_configured(settings)
        or row.expires_at is None
        or row.expires_at <= now
    ):
        return None
    return row.token


@dataclass(frozen=True)
class Status:
    """What the Superuser sees about the connection (never the tokens)."""

    configured: bool
    connected: bool
    account_name: str | None
    connected_at: datetime | None
    expires_at: datetime | None
    refresh_expires_at: datetime | None
    error: str | None


def status(session: Session, settings: Settings, now: datetime) -> Status:
    row = session.get(ChannelToken, CHANNEL)
    configured = tiktok.is_configured(settings)
    if row is None:
        return Status(configured, False, None, None, None, None, None)
    connected = access_token(session, settings, now) is not None
    error = row.refresh_error
    if configured and not connected and error is None:
        error = EXPIRED
    return Status(
        configured=configured,
        connected=connected,
        account_name=row.account_name,
        connected_at=row.connected_at,
        expires_at=row.expires_at,
        refresh_expires_at=row.refresh_expires_at,
        error=error,
    )
