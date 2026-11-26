"""VIVES login through Authentik (spec #160, ADR 0011): OpenID Connect with the
Authorization Code flow and PKCE. The frontend only redirects the browser; the
backend exchanges the code, checks the ID token (signature from Authentik's
keys, issuer, audience, nonce, expiry) and turns its claims into a User:
created at the first login, then linked by Authentik's `sub`. The Role comes
from exactly one Role group, a Student's Programme and Year from attributes;
name and email follow Authentik at every login."""

import logging
import secrets
import time
from dataclasses import dataclass, field
from typing import Protocol

import httpx
import jwt
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from pmp_backend.domain import Role, Year
from pmp_backend.errors import Forbidden, Unavailable
from pmp_backend.models import Programme, User
from pmp_backend.security import hash_password
from pmp_backend.services.users import why_linked
from pmp_backend.settings import Settings

log = logging.getLogger(__name__)

SCOPES = "openid email profile"
TIMEOUT_SECONDS = 20
# Authentik's configuration and keys are fetched again after this.
CACHE_SECONDS = 600
DEFAULT_GROUPS = {
    Role.SUPERUSER.value: "pmp-superusers",
    Role.TEACHER.value: "pmp-teachers",
    Role.STUDENT.value: "pmp-students",
    Role.CLIENT.value: "pmp-clients",
}
ASK = "Ask the Superuser."


class VivesLoginError(Forbidden):
    """The login was refused; the message is fit to show to the person."""


class VivesLoginUnavailableError(Unavailable):
    """Authentik can't be reached or answers nonsense."""


@dataclass(frozen=True)
class Config:
    issuer: str
    client_id: str
    client_secret: str
    # Role -> the Authentik group that gives it.
    groups: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_GROUPS))
    programme_claim: str = "programme"
    year_claim: str = "year"


def config_from(settings: Settings) -> Config | None:
    """The connection from AUTHENTIK_* in the environment, or None. (The
    Superuser's setup screen comes with #162.)"""
    secret = settings.authentik_client_secret
    if not (
        settings.authentik_issuer_url
        and settings.authentik_client_id
        and secret
        and secret.get_secret_value()
    ):
        return None
    return Config(
        issuer=settings.authentik_issuer_url,
        client_id=settings.authentik_client_id,
        client_secret=secret.get_secret_value(),
    )


def redirect_uri(settings: Settings) -> str:
    """Where Authentik sends the browser back: the frontend's callback."""
    return f"{settings.site_url.rstrip('/')}/auth/callback"


class Oidc(Protocol):
    """Authentik's endpoints; tests use testing.FakeAuthentik."""

    def discovery(self, issuer: str) -> dict: ...

    def jwks(self, uri: str) -> dict: ...

    def token(self, endpoint: str, form: dict[str, str]) -> dict: ...


class HttpOidc:
    """Authentik over HTTPS, with its configuration and keys cached."""

    def __init__(self) -> None:
        self._client = httpx.Client(timeout=TIMEOUT_SECONDS)
        self._cache: dict[str, tuple[float, dict]] = {}

    def _get(self, url: str) -> dict:
        found = self._cache.get(url)
        if found and time.monotonic() - found[0] < CACHE_SECONDS:
            return found[1]
        try:
            response = self._client.get(url)
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise VivesLoginUnavailableError(
                f"VIVES login can't be reached right now ({error})."
            ) from error
        self._cache[url] = (time.monotonic(), body)
        return body

    def discovery(self, issuer: str) -> dict:
        return self._get(f"{issuer.rstrip('/')}/.well-known/openid-configuration")

    def jwks(self, uri: str) -> dict:
        return self._get(uri)

    def token(self, endpoint: str, form: dict[str, str]) -> dict:
        try:
            response = self._client.post(endpoint, data=form)
        except httpx.HTTPError as error:
            raise VivesLoginUnavailableError(
                f"VIVES login can't be reached right now ({error})."
            ) from error
        try:
            body = response.json()
        except ValueError:
            body = {}
        if response.status_code >= 400 or "id_token" not in body:
            reason = (
                body.get("error_description")
                or body.get("error")
                or response.status_code
            )
            raise VivesLoginError(
                f"VIVES login refused the login ({reason}). Try again."
            )
        return body


@dataclass(frozen=True)
class Start:
    """What the frontend needs to send the browser to Authentik."""

    authorization_endpoint: str
    client_id: str
    scope: str
    redirect_uri: str


def start(oidc: Oidc, config: Config, settings: Settings) -> Start:
    found = oidc.discovery(config.issuer)
    try:
        endpoint = found["authorization_endpoint"]
    except KeyError as error:
        raise VivesLoginUnavailableError(
            "The Issuer URL doesn't point to an OpenID provider."
        ) from error
    return Start(endpoint, config.client_id, SCOPES, redirect_uri(settings))


def claims_of(
    oidc: Oidc,
    config: Config,
    settings: Settings,
    *,
    code: str,
    code_verifier: str,
    nonce: str,
) -> dict:
    """Exchange the code and return the checked ID token's claims."""
    found = oidc.discovery(config.issuer)
    try:
        token_endpoint, jwks_uri = found["token_endpoint"], found["jwks_uri"]
    except KeyError as error:
        raise VivesLoginUnavailableError(
            "The Issuer URL doesn't point to an OpenID provider."
        ) from error
    answer = oidc.token(
        token_endpoint,
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri(settings),
            "client_id": config.client_id,
            "client_secret": config.client_secret,
            "code_verifier": code_verifier,
        },
    )
    keys = jwt.PyJWKSet.from_dict(oidc.jwks(jwks_uri))
    id_token = answer["id_token"]
    try:
        header = jwt.get_unverified_header(id_token)
        key = next(
            (
                k
                for k in keys.keys
                if not header.get("kid") or k.key_id == header["kid"]
            ),
            None,
        )
        if key is None:
            raise jwt.InvalidTokenError("no matching key")
        algorithms = found.get("id_token_signing_alg_values_supported") or ["RS256"]
        claims = jwt.decode(
            id_token,
            key.key,
            algorithms=[a for a in algorithms if a != "none"],
            audience=config.client_id,
            issuer=found.get("issuer", config.issuer),
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.PyJWTError as error:
        log.warning("A VIVES login token was refused: %s", error)
        raise VivesLoginError(
            "VIVES login sent a token the platform can't trust. Try again."
        ) from error
    if not nonce or not secrets.compare_digest(str(claims.get("nonce", "")), nonce):
        raise VivesLoginError("This login link was already used or expired. Try again.")
    return claims


@dataclass(frozen=True)
class Identity:
    """Who the claims say someone is, and what they get on the platform."""

    sub: str
    email: str
    first_name: str
    last_name: str
    role: str
    groups: list[str]
    programme: str | None
    year: str | None


def _names(claims: dict) -> tuple[str, str]:
    first = str(claims.get("given_name") or "").strip()
    last = str(claims.get("family_name") or "").strip()
    if first and last and first != last:
        return first[:100], last[:100]
    full = str(claims.get("name") or first or "").strip()
    head, _, tail = full.partition(" ")
    return (head or "VIVES")[:100], (tail or "-")[:100]


def identity(config: Config, claims: dict) -> Identity:
    """The claims as an Identity, or VivesLoginError saying what is missing."""
    email = str(claims.get("email") or "").strip().lower()
    if not email or claims.get("email_verified") is False:
        raise VivesLoginError(f"Your VIVES login has no verified email. {ASK}")
    raw_groups = claims.get("groups") or []
    groups = (
        [str(group) for group in raw_groups] if isinstance(raw_groups, list) else []
    )
    roles = [role for role, group in config.groups.items() if group in groups]
    if not roles:
        raise VivesLoginError(
            f"You have no role on the platform in VIVES login "
            f"(none of {', '.join(config.groups.values())}). {ASK}"
        )
    if len(roles) > 1:
        clash = ", ".join(config.groups[role] for role in roles)
        raise VivesLoginError(
            f"You are in more than one platform group in VIVES login ({clash}). {ASK}"
        )
    role = roles[0]
    programme = year = None
    if role == Role.STUDENT.value:
        programme = str(claims.get(config.programme_claim) or "").strip()
        year = str(claims.get(config.year_claim) or "").strip()
        years = {member.value.lower(): member.value for member in Year}
        if not programme or year.lower() not in years:
            raise VivesLoginError(
                f"Your programme or year is missing in VIVES login. {ASK}"
            )
        year = years[year.lower()]
    first, last = _names(claims)
    return Identity(
        sub=str(claims["sub"]),
        email=email,
        first_name=first,
        last_name=last,
        role=role,
        groups=groups,
        programme=programme[:100] if programme else None,
        year=year,
    )


def _programme(session: Session, name: str) -> str:
    """The Programme as the list spells it; added when it isn't there yet."""
    found = session.scalar(
        select(Programme).where(func.lower(Programme.name) == name.lower())
    )
    if found is not None:
        return found.name
    session.add(Programme(name=name))
    session.flush()
    return name


def user_for(session: Session, found: Identity) -> User:
    """The platform's User for this Identity: by `sub`, else by email, else
    new; brought in line with Authentik. Refused for a deactivated User and
    for a Role change while the old Role still has links."""
    user = session.scalar(
        select(User).where(User.authentik_sub == found.sub).with_for_update()
    ) or session.scalar(select(User).where(User.email == found.email).with_for_update())
    if user is None:
        user = User(
            first_name=found.first_name,
            last_name=found.last_name,
            email=found.email,
            # Nobody can log in with it: VIVES login has no password.
            password_hash=hash_password(secrets.token_urlsafe(32)),
            role=found.role,
            programme=_programme(session, found.programme) if found.programme else None,
            year=found.year,
            authentik_sub=found.sub,
            must_change_password=False,
        )
        session.add(user)
        session.commit()
        log.info("VIVES login created User %s (%s)", user.id, user.role)
        return user
    if not user.is_active:
        raise VivesLoginError(
            "Your platform account is deactivated. Ask the Superuser."
        )
    if user.role != found.role:
        # The links that keep a User from being deleted keep the Role too.
        reason = why_linked(session, user)
        if reason is not None:
            session.rollback()
            raise VivesLoginError(
                "Your role changed in VIVES login, but on the platform "
                f"{user.full_name} {reason}. {ASK}"
            )
        user.role = found.role
        if found.role != Role.CLIENT.value:
            user.organisation = None
        if found.role != Role.STUDENT.value:
            user.programme = user.year = None
    if found.role == Role.STUDENT.value:
        user.programme = _programme(session, found.programme)
        user.year = found.year
    user.authentik_sub = found.sub
    user.first_name, user.last_name = found.first_name, found.last_name
    if user.email != found.email:
        taken = session.scalar(
            select(User.id).where(User.email == found.email, User.id != user.id)
        )
        if taken is None:
            user.email = found.email
    user.must_change_password = False
    session.commit()
    return user


def log_in(
    session: Session,
    oidc: Oidc,
    config: Config,
    settings: Settings,
    *,
    code: str,
    code_verifier: str,
    nonce: str,
) -> User:
    claims = claims_of(
        oidc, config, settings, code=code, code_verifier=code_verifier, nonce=nonce
    )
    return user_for(session, identity(config, claims))
