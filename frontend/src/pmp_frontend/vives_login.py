"""VIVES login through Authentik (spec #160, ADR 0011): the frontend only sends
the browser to Authentik and receives it back at /auth/callback; the backend
exchanges the code and checks the token. The `state`, `nonce` and PKCE
verifier stay in this browser's session storage until the callback."""

import base64
import hashlib
import secrets
from typing import Any
from urllib.parse import urlencode

from nicegui import app, ui

from pmp_frontend import api
from pmp_frontend.shell import TOKEN_KEY, ErrorMessage, home
from pmp_frontend.theme import frame

PENDING_KEY = "vives_login"
# The Setup test's report, shown once on the VIVES login screen (#162).
TEST_REPORT_KEY = "vives_login_test_report"
OLD_LINK = "This login link is old or was already used. Try again."


def _challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def authorize_url(start: dict[str, Any], purpose: str = "login") -> str:
    """Authentik's login page for a fresh login (or the Superuser's Setup
    test, #162), remembering its secrets."""
    state = secrets.token_urlsafe(24)
    nonce = secrets.token_urlsafe(24)
    verifier = secrets.token_urlsafe(48)
    app.storage.user[PENDING_KEY] = {
        "state": state,
        "nonce": nonce,
        "verifier": verifier,
        "purpose": purpose,
    }
    query = urlencode(
        {
            "response_type": "code",
            "client_id": start["client_id"],
            "redirect_uri": start["redirect_uri"],
            "scope": start["scope"],
            "state": state,
            "nonce": nonce,
            "code_challenge": _challenge(verifier),
            "code_challenge_method": "S256",
        }
    )
    return f"{start['authorization_endpoint']}?{query}"


def leave(url: str) -> None:
    """Send the browser to Authentik (tests replace this)."""
    ui.navigate.to(url)


def login_card(start: dict[str, Any] | None) -> None:
    """The "Log in with VIVES" card on the login page, when it is set up."""
    if not start or not start.get("configured"):
        return
    with ui.card().classes("w-full max-w-md").mark("vives-login-card"):
        ui.label("VIVES login").classes("text-h6")
        ui.label("Students, staff and clients log in with their VIVES login.").classes(
            "text-caption"
        )
        ui.button(
            "Log in with VIVES",
            icon="login",
            on_click=lambda: leave(authorize_url(start)),
        ).classes("w-full").mark("vives-log-in")


def register() -> None:
    @ui.page("/auth/break-glass")
    async def break_glass(code: str | None = None) -> None:
        """A one-time login link made on the VM (#163)."""
        with frame("Log in"), ui.column().classes("w-full items-center gap-4 pt-8"):
            with ui.card().classes("w-full max-w-md").mark("break-glass"):
                ui.label("One-time login").classes("text-h6")
                problem = ErrorMessage()
            try:
                token, user = await api.break_glass(code or "")
            except api.ApiError as failure:
                problem.show(failure.message)
                return
            app.storage.user[TOKEN_KEY] = token
            ui.navigate.to(home(user))

    @ui.page("/auth/callback")
    async def callback(
        code: str | None = None,
        state: str | None = None,
        error: str | None = None,
        error_description: str | None = None,
    ) -> None:
        pending = app.storage.user.pop(PENDING_KEY, None)
        with frame("Log in"), ui.column().classes("w-full items-center gap-4 pt-8"):
            with ui.card().classes("w-full max-w-md").mark("vives-callback"):
                ui.label("VIVES login").classes("text-h6")
                problem = ErrorMessage()
                ui.link("Back to the login page", "/login").mark("back-to-login")
            if error:
                problem.show(f"VIVES login: {error_description or error}")
                return
            if not pending or not code or state != pending["state"]:
                problem.show(OLD_LINK)
                return
            if pending.get("purpose") == "test":
                try:
                    report = await api.vives_login_setup_test(
                        app.storage.user.get(TOKEN_KEY, ""),
                        code,
                        pending["verifier"],
                        pending["nonce"],
                    )
                except api.ApiError as failure:
                    problem.show(failure.message)
                    return
                app.storage.user[TEST_REPORT_KEY] = report
                ui.navigate.to("/vives-login")
                return
            try:
                token, user = await api.vives_login(
                    code, pending["verifier"], pending["nonce"]
                )
            except api.ApiError as failure:
                problem.show(failure.message)
                return
            app.storage.user[TOKEN_KEY] = token
            ui.navigate.to(home(user))
