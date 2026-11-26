"""VIVES login on the login page and its callback (spec #160, #161)."""

from urllib.parse import parse_qs, urlsplit

import pytest
from nicegui import app
from nicegui.testing import User

from pmp_frontend.vives_login import OLD_LINK, PENDING_KEY


@pytest.fixture
def leaving(monkeypatch) -> list[str]:
    """The addresses the browser is sent to (Authentik's login page can't be
    opened in tests)."""
    sent: list[str] = []
    # By name: the app (and this module) is loaded again for every test.
    monkeypatch.setattr("pmp_frontend.vives_login.leave", sent.append)
    return sent


async def go_to_authentik(user: User, leaving: list[str]) -> dict:
    """Click Log in with VIVES; the query of Authentik's login page."""
    await user.open("/login")
    await user.should_see(marker="vives-log-in")
    user.find(marker="vives-log-in").click()
    url = leaving[-1]
    return {key: value[0] for key, value in parse_qs(urlsplit(url).query).items()}


async def test_the_button_sends_the_browser_to_authentik(
    user: User, leaving: list[str]
) -> None:
    query = await go_to_authentik(user, leaving)

    assert query["client_id"] == "pmp-test-client"
    assert query["redirect_uri"] == "https://10.20.10.33/auth/callback"
    assert query["scope"] == "openid email profile"
    assert query["response_type"] == "code"
    assert query["code_challenge_method"] == "S256"
    assert len(query["state"]) >= 32 and len(query["nonce"]) >= 32


async def test_the_callback_logs_in(
    user: User, backend_in_process, leaving: list[str]
) -> None:
    query = await go_to_authentik(user, leaving)
    authentik = backend_in_process.state.oidc
    code = authentik.issue(
        authentik.claims(groups=["pmp-teachers"]), nonce=query["nonce"]
    )

    await user.open(f"/auth/callback?code={code}&state={query['state']}")

    await user.should_see(marker="navigation", retries=30)
    await user.should_see("Projects")


async def test_a_wrong_state_is_refused(user: User, leaving: list[str]) -> None:
    await go_to_authentik(user, leaving)

    await user.open("/auth/callback?code=code-1&state=someone-else")

    await user.should_see(OLD_LINK)
    await user.should_see(marker="back-to-login")


async def test_an_error_from_authentik_is_shown(user: User) -> None:
    await user.open(
        "/auth/callback?error=access_denied&error_description=The+user+cancelled"
    )

    await user.should_see("VIVES login: The user cancelled")


async def test_a_refused_login_shows_why(
    user: User, backend_in_process, leaving: list[str]
) -> None:
    query = await go_to_authentik(user, leaving)
    authentik = backend_in_process.state.oidc
    code = authentik.issue(authentik.claims(groups=[]), nonce=query["nonce"])

    await user.open(f"/auth/callback?code={code}&state={query['state']}")

    await user.should_see("You have no role on the platform", retries=30)
    assert PENDING_KEY not in app.storage.user
