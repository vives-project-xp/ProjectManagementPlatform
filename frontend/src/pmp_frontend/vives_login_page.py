"""The VIVES login screen (spec #160, #162): the Superuser connects the platform
to VIVES' Authentik, runs a Setup test and switches it on. docs/authentik.md
walks through it next to Authentik's admin panel."""

from typing import Any

from nicegui import app, ui

from pmp_frontend import api
from pmp_frontend.shell import ErrorMessage, confirm, role_page, token
from pmp_frontend.times import shown
from pmp_frontend.vives_login import TEST_REPORT_KEY, authorize_url, leave

ROLES = [
    ("superuser", "Superuser"),
    ("teacher", "Teacher"),
    ("student", "Student"),
    ("client", "Client"),
]
REPORT_KEY = TEST_REPORT_KEY
SWITCH_ON_QUESTION = (
    "Switch on VIVES login? From then on nobody can log in with a password on "
    "the site, the Test login is gone, and VIVES login can only be switched off "
    "on the server (docs/authentik.md)."
)


def _status(found: dict[str, Any]) -> None:
    with ui.card().classes("w-full max-w-2xl").mark("vives-login-on"):
        ui.label("VIVES login is on").classes("text-h6")
        ui.label(
            f"Switched on {shown(found['enabled_at'])}"
            + (f" by {found['enabled_by']}" if found["enabled_by"] else "")
            + "."
        )
        ui.label(f"Issuer: {found['issuer_url']}").classes("break-all")
        for role, label in ROLES:
            ui.label(f"{label}: {found['groups'][role]}").classes("text-caption")
        ui.label(
            "Switching it off is only possible on the server (see docs/authentik.md)."
        ).classes("text-caption")


def _report(report: dict[str, Any]) -> None:
    with ui.card().classes("w-full max-w-2xl").mark("vives-login-report"):
        ui.label("Setup test: what VIVES login sent").classes("text-h6")
        for label, value in (
            ("Email", report["email"]),
            ("Name", report["name"]),
            ("Groups", ", ".join(report["groups"]) or "(none)"),
            ("Programme", report["programme"]),
            ("Year", report["year"]),
        ):
            ui.label(f"{label}: {value or '–'}")
        if report["role"]:
            ui.label(f"This login gives the Role: {report['role']}.").classes(
                "font-medium"
            ).mark("vives-login-test-role")
        else:
            with ui.row().classes("items-center gap-2 no-wrap"):
                ui.icon("warning", color="primary")
                ui.label(f"Refused: {report['refusal']}").mark(
                    "vives-login-test-refused"
                )


def _setup(found: dict[str, Any], reload) -> None:
    env = found["from_environment"]

    async def save() -> bool:
        body = {
            "groups": {role: groups[role].value or "" for role, _ in ROLES},
            "programme_claim": programme.value or "",
            "year_claim": year.value or "",
        }
        if not env:
            body |= {
                "issuer_url": issuer.value or None,
                "client_id": client.value or None,
                "client_secret": secret.value or None,
            }
        try:
            await api.save_vives_login(token(), body)
        except api.ApiError as problem:
            error.show(problem.message)
            return False
        error.hide()
        return True

    async def save_clicked() -> None:
        if await save():
            ui.notify("Saved. Run the Setup test again before switching on.")
            await reload()

    async def check() -> None:
        if not await save():
            return
        try:
            answer = await api.check_vives_login(token())
        except api.ApiError as problem:
            error.show(problem.message)
            return
        ui.notify(answer["message"])
        checked.text = answer["message"]

    async def test_login() -> None:
        if not await save():
            return
        try:
            start = await api.vives_login_test_start(token())
        except api.ApiError as problem:
            error.show(problem.message)
            return
        leave(authorize_url(start, purpose="test"))

    async def switch_on() -> None:
        if not await confirm(SWITCH_ON_QUESTION, "Switch on"):
            return
        try:
            await api.switch_on_vives_login(token())
        except api.ApiError as problem:
            error.show(problem.message)
            return
        ui.notify("VIVES login is on.")
        await reload()

    with ui.card().classes("w-full max-w-2xl").mark("vives-login-step-1"):
        ui.label("1. In Authentik").classes("text-h6")
        ui.label(
            "Create an OAuth2/OpenID provider (confidential) and an application "
            "for it, as docs/authentik.md shows. Use this redirect URI:"
        )
        with ui.row().classes("items-center gap-2 no-wrap w-full"):
            ui.label(found["redirect_uri"]).classes("font-mono break-all").mark(
                "vives-login-redirect-uri"
            )
            ui.button(
                icon="content_copy",
                on_click=lambda: (
                    ui.clipboard.write(found["redirect_uri"]),
                    ui.notify("Copied."),
                ),
            ).props("flat dense color=dark").tooltip("Copy")
        ui.label(f"Scopes: {found['scope']} (with the groups in the token).").classes(
            "text-caption"
        )
    with ui.card().classes("w-full max-w-2xl").mark("vives-login-step-2"):
        ui.label("2. The connection").classes("text-h6")
        if env:
            ui.label(
                "Set on the server (AUTHENTIK_* in /opt/pmp/.env): "
                f"{found['issuer_url']}, client {found['client_id']}."
            ).mark("vives-login-from-env")
        issuer = (
            ui.input(
                "Issuer URL (https://…/application/o/<slug>/)",
                value=found["issuer_url"] or "",
            )
            .classes("w-full")
            .mark("vives-login-issuer")
        )
        client = (
            ui.input("Client ID", value=found["client_id"] or "")
            .classes("w-full")
            .mark("vives-login-client-id")
        )
        secret = (
            ui.input(
                "Client secret"
                + (" (stored: leave empty to keep it)" if found["secret_set"] else ""),
                password=True,
            )
            .classes("w-full")
            .mark("vives-login-secret")
        )
        for field in (issuer, client, secret):
            if env:
                field.disable()
        ui.label("Authentik groups for the Roles").classes("font-medium")
        groups = {}
        with ui.row().classes("w-full"):
            for role, label in ROLES:
                groups[role] = ui.input(label, value=found["groups"][role]).mark(
                    f"vives-login-group-{role}"
                )
        ui.label("Students' attributes in the token").classes("font-medium")
        with ui.row():
            programme = ui.input("Programme", value=found["programme_claim"]).mark(
                "vives-login-programme-claim"
            )
            year = ui.input("Year", value=found["year_claim"]).mark(
                "vives-login-year-claim"
            )
        error = ErrorMessage()
        with ui.row().classes("items-center gap-2"):
            ui.button("Save", on_click=save_clicked).mark("save-vives-login")
            ui.button("Check the connection", on_click=check).props(
                "outline color=dark"
            ).mark("check-vives-login")
        checked = ui.label().classes("text-caption").mark("vives-login-checked")
    with ui.card().classes("w-full max-w-2xl").mark("vives-login-step-3"):
        ui.label("3. Setup test").classes("text-h6")
        ui.label(
            "Log in once through VIVES login with your own account: the platform "
            "shows what it received and which Role that gives. Nobody is created."
        )
        ui.button("Test login", icon="login", on_click=test_login).mark(
            "test-vives-login"
        )
        if found["tested_at"]:
            ui.label(
                f"Last test {shown(found['tested_at'])}: "
                + (found["tested_role"] or "refused")
                + ("" if found["test_is_current"] else " (settings changed since)")
            ).classes("text-caption")
    ready = found["test_is_current"] and found["tested_role"] == "superuser"
    with ui.card().classes("w-full max-w-2xl").mark("vives-login-step-4"):
        ui.label("4. Switch on").classes("text-h6")
        ui.label(
            "Possible after a Setup test, with the settings as they are, that gave "
            "you the Superuser Role, so you can always get back in."
        ).classes("text-caption")
        button = ui.button("Switch on", icon="power_settings_new", on_click=switch_on)
        button.mark("switch-on-vives-login")
        if not ready:
            button.disable()


def register() -> None:
    @role_page("/vives-login", "VIVES login", {"superuser"})
    async def vives_login_page(user: api.CurrentUser) -> None:
        @ui.refreshable
        async def content() -> None:
            found = await api.vives_login_screen(token())
            report = app.storage.user.pop(REPORT_KEY, None)
            if report:
                _report(report)
            if found["enabled_at"]:
                _status(found)
            else:
                _setup(found, content.refresh)

        await content()
