"""The VIVES login screen (spec #160, #162)."""

import asyncio
import sys

import pytest
from nicegui.testing import User

from pmp_backend.services import vives_login
from pmp_backend.testing import FakeAuthentik
from tests.conftest import ready_to_work
from tests.test_vives_login import switch_on


@pytest.fixture
def leaving(monkeypatch, user: User) -> list[str]:
    sent: list[str] = []
    # The modules as loaded for this test (the app is loaded again per test).
    for name in ("pmp_frontend.vives_login", "pmp_frontend.vives_login_page"):
        monkeypatch.setattr(sys.modules[name], "leave", sent.append)
    return sent


async def test_the_screen_shows_the_redirect_uri(user: User) -> None:
    await ready_to_work(user, "superuser")
    await user.open("/vives-login")

    await user.should_see("https://10.20.10.33/auth/callback")
    await user.should_see(marker="vives-login-from-env")
    switch = user.find(marker="switch-on-vives-login").elements.pop()
    assert not switch.enabled


async def test_a_setup_test_then_switch_on(
    user: User, backend_in_process, leaving: list[str]
) -> None:
    await ready_to_work(user, "superuser")
    await user.open("/vives-login")
    await user.should_see(marker="test-vives-login")

    user.find(marker="test-vives-login").click()
    for _ in range(100):
        if leaving:
            break
        await asyncio.sleep(0.05)
    url = leaving[-1]
    assert url.startswith("https://auth.example.org/application/o/authorize/")
    query = dict(part.split("=", 1) for part in url.split("?", 1)[1].split("&"))
    authentik: FakeAuthentik = backend_in_process.state.oidc
    code = authentik.issue(
        authentik.claims(
            sub="s-super", email="super@vives.be", groups=["pmp-superusers"]
        ),
        nonce=query["nonce"],
    )

    await user.open(f"/auth/callback?code={code}&state={query['state']}")

    await user.should_see(marker="vives-login-report", retries=30)
    await user.should_see("This login gives the Role: superuser.")
    switch = user.find(marker="switch-on-vives-login").elements.pop()
    assert switch.enabled
    user.find(marker="switch-on-vives-login").click()
    await user.should_see("Switch on VIVES login?")
    user.find(marker="confirm").click()
    await user.should_see(marker="vives-login-on", retries=30)
    with backend_in_process.state.sessionmaker() as session:
        assert vives_login.is_on(session)


async def test_switched_on_the_site_has_only_vives_login(
    user: User, backend_in_process
) -> None:
    await ready_to_work(user, "superuser")
    switch_on(backend_in_process)

    await user.open("/login")
    await user.should_see(marker="vives-log-in")
    await user.should_not_see(marker="log-in")
    await user.should_not_see(marker="email")

    await user.open("/account")
    await user.should_see("My account")
    await user.should_not_see(marker="change-password")

    await user.open("/users")
    await user.should_see(marker="users-from-vives-login")
    await user.should_not_see(marker="new-user")


async def test_a_break_glass_link_logs_in(user: User, backend_in_process) -> None:
    from pmp_backend.services import break_glass

    await ready_to_work(user, "superuser")
    switch_on(backend_in_process)
    with backend_in_process.state.sessionmaker() as session:
        _, code = break_glass.create(session, None)

    await user.open(f"/auth/break-glass?code={code}")
    await user.should_see(marker="navigation", retries=30)

    await user.open("/auth/break-glass?code=wrong")
    await user.should_see("This login link is wrong, used or expired.")
