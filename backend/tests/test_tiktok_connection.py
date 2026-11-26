"""Connecting the TikTok account and keeping its token fresh (spec #145, #146)."""

from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from pmp_backend import testing
from pmp_backend.models import ChannelToken
from pmp_backend.services import tiktok_connection
from tests.conftest import ready_to_work

BRUSSELS = ZoneInfo("Europe/Brussels")
REDIRECT = "https://github.com/vives-project-xp/ProjectManagementPlatform"


def status(client: TestClient, staff: dict) -> dict:
    response = client.get("/api/social/tiktok", headers=staff)
    assert response.status_code == 200, response.text
    return response.json()


def state_of(url: str) -> str:
    return parse_qs(urlsplit(url).query)["state"][0]


def connect(client: TestClient, staff: dict, pasted: str):
    return client.post(
        "/api/social/tiktok/connect", json={"pasted": pasted}, headers=staff
    )


def redirected(state: str, code: str = "abc%2A123%21") -> str:
    """The address TikTok sends the Superuser to after logging in."""
    return f"{REDIRECT}?code={code}&scopes=user.info.basic%2Cvideo.upload&state={state}"


def connected(client: TestClient, staff: dict) -> dict:
    url = status(client, staff)["connect_url"]
    response = connect(client, staff, redirected(state_of(url)))
    assert response.status_code == 200, response.text
    return response.json()


def test_the_superuser_gets_a_login_link_with_the_apps_scopes(client: TestClient):
    staff = ready_to_work(client, "superuser")

    found = status(client, staff)

    assert found["configured"] and not found["connected"]
    assert found["account_name"] is None and found["error"] is None
    query = parse_qs(urlsplit(found["connect_url"]).query)
    assert found["connect_url"].startswith("https://www.tiktok.com/v2/auth/authorize/")
    assert query["client_key"] == ["test-tiktok-key"]
    assert query["scope"] == ["user.info.basic,video.upload,video.publish"]
    assert query["response_type"] == ["code"]
    assert query["redirect_uri"] == [REDIRECT]


def test_pasting_the_address_connects_the_account(
    client: TestClient, tiktok: testing.FakeTikTok
):
    staff = ready_to_work(client, "superuser")

    found = connected(client, staff)

    # The code comes out of the address decoded, the tokens never go out.
    assert tiktok.codes == ["abc*123!"]
    assert found["connected"] and found["account_name"] == "VIVES test"
    assert found["connected_at"] is not None and found["error"] is None
    assert "access-1" not in str(found) and "refresh-1" not in str(found)
    with client.app.state.sessionmaker() as session:
        row = session.get(ChannelToken, "tiktok")
        assert (row.token, row.refresh_token) == ("access-1", "refresh-1")


def test_a_bare_code_also_connects(client: TestClient, tiktok: testing.FakeTikTok):
    staff = ready_to_work(client, "superuser")

    response = connect(client, staff, "  code-only  ")

    assert response.status_code == 200, response.text
    assert tiktok.codes == ["code-only"]


@pytest.mark.parametrize(
    "pasted",
    [
        redirected("123.not-our-signature"),
        redirected("not-even-a-state"),
        f"{REDIRECT}?code=abc",
    ],
)
def test_an_address_from_another_link_is_refused(
    client: TestClient, tiktok: testing.FakeTikTok, pasted: str
):
    staff = ready_to_work(client, "superuser")

    response = connect(client, staff, pasted)

    assert response.status_code == 422
    assert "Connect TikTok again" in response.json()["detail"]
    assert tiktok.codes == []


def test_an_old_link_is_refused(client: TestClient, tiktok: testing.FakeTikTok):
    staff = ready_to_work(client, "superuser")
    settings = client.app.state.settings
    user_id = client.get("/api/auth/me", headers=staff).json()["id"]
    old = datetime.now(BRUSSELS) - timedelta(hours=1)

    response = connect(
        client, staff, redirected(tiktok_connection.make_state(settings, user_id, old))
    )

    assert response.status_code == 422
    assert tiktok.codes == []


def test_a_refused_login_or_code_says_why(
    client: TestClient, tiktok: testing.FakeTikTok
):
    staff = ready_to_work(client, "superuser")
    state = state_of(status(client, staff)["connect_url"])

    denied = connect(
        client,
        staff,
        f"{REDIRECT}?error=access_denied&error_description=User+cancelled&state={state}",
    )
    tiktok.refused.add("used")
    used = connect(client, staff, redirected(state, code="used"))

    assert denied.status_code == 422
    assert denied.json()["detail"] == "TikTok didn't connect: User cancelled"
    assert used.status_code == 422
    assert "a code works only once" in used.json()["detail"]
    assert not status(client, staff)["connected"]


def test_tiktok_down_is_a_503(client: TestClient, tiktok: testing.FakeTikTok):
    staff = ready_to_work(client, "superuser")
    tiktok.failing = True

    response = connect(client, staff, "some-code")

    assert response.status_code == 503


@pytest.mark.parametrize("role", ["teacher", "student"])
def test_only_the_superuser_connects(client: TestClient, role: str):
    other = ready_to_work(client, role)

    assert client.get("/api/social/tiktok", headers=other).status_code == 403
    assert connect(client, other, "some-code").status_code == 403


# Refreshing


def set_expiry(client: TestClient, expires_at: datetime) -> None:
    with client.app.state.sessionmaker() as session:
        row = session.get(ChannelToken, "tiktok")
        row.expires_at = expires_at
        session.commit()


def refresh(client: TestClient, tiktok: testing.FakeTikTok, now: datetime) -> bool:
    with client.app.state.sessionmaker() as session:
        return tiktok_connection.refresh_due(
            session, tiktok, client.app.state.settings, now
        )


def test_the_token_is_refreshed_shortly_before_it_runs_out(
    client: TestClient, tiktok: testing.FakeTikTok
):
    staff = ready_to_work(client, "superuser")
    connected(client, staff)
    now = datetime.now(BRUSSELS)

    assert not refresh(client, tiktok, now)
    set_expiry(client, now + timedelta(hours=1))
    assert refresh(client, tiktok, now)

    assert tiktok.refreshes == ["refresh-1"]
    with client.app.state.sessionmaker() as session:
        row = session.get(ChannelToken, "tiktok")
        assert (row.token, row.refresh_token) == ("access-101", "refresh-101")
    assert status(client, staff)["connected"]


def test_a_failed_refresh_is_shown_and_tried_again_later(
    client: TestClient, tiktok: testing.FakeTikTok
):
    staff = ready_to_work(client, "superuser")
    connected(client, staff)
    now = datetime.now(BRUSSELS)
    set_expiry(client, now + timedelta(minutes=30))
    tiktok.refresh_failing = True

    assert not refresh(client, tiktok, now)
    # Still working on the old token, with a notice.
    found = status(client, staff)
    assert found["connected"]
    assert found["error"] == "TikTok answered 400: invalid_grant"
    # Not again at once; again half an hour later, which works.
    tiktok.refresh_failing = False
    assert not refresh(client, tiktok, now + timedelta(minutes=5))
    assert refresh(client, tiktok, now + timedelta(minutes=31))
    assert status(client, staff)["error"] is None


def test_an_expired_connection_asks_to_connect_again(
    client: TestClient, tiktok: testing.FakeTikTok
):
    staff = ready_to_work(client, "superuser")
    connected(client, staff)
    set_expiry(client, datetime.now(BRUSSELS) - timedelta(minutes=1))

    found = status(client, staff)

    assert not found["connected"]
    assert found["error"] == tiktok_connection.EXPIRED
    with client.app.state.sessionmaker() as session:
        settings = client.app.state.settings
        now = datetime.now(BRUSSELS)
        assert tiktok_connection.access_token(session, settings, now) is None


def test_a_refresh_token_that_ran_out_is_not_used(
    client: TestClient, tiktok: testing.FakeTikTok
):
    staff = ready_to_work(client, "superuser")
    connected(client, staff)
    now = datetime.now(BRUSSELS)
    with client.app.state.sessionmaker() as session:
        row = session.get(ChannelToken, "tiktok")
        row.expires_at = now - timedelta(hours=1)
        row.refresh_expires_at = now - timedelta(minutes=1)
        session.commit()

    assert not refresh(client, tiktok, now)

    assert tiktok.refreshes == []
    assert status(client, staff)["error"] == tiktok_connection.EXPIRED


# Posting-time settings


def test_tiktok_posting_times_have_defaults_and_can_change(client: TestClient):
    staff = ready_to_work(client, "superuser")
    found = client.get("/api/social/settings", headers=staff).json()
    assert (found["tiktok_weekdays"], found["tiktok_times"]) == (
        [0, 1, 2, 3, 4],
        ["17:00"],
    )
    assert (found["slideshow_weekday"], found["slideshow_time"]) == (4, "18:00")
    assert (found["slideshow_cutoff_weekday"], found["slideshow_cutoff_time"]) == (
        4,
        "12:00",
    )

    changed = found | {
        "tiktok_weekdays": [1, 3],
        "tiktok_times": ["16:30"],
        "slideshow_weekday": 3,
        "slideshow_time": "19:00",
        "slideshow_cutoff_weekday": 3,
        "slideshow_cutoff_time": "09:00",
    }
    response = client.put("/api/social/settings", json=changed, headers=staff)
    assert response.status_code == 200, response.text
    assert response.json() == changed

    # Leaving the TikTok settings out keeps them.
    instagram_only = {
        key: changed[key]
        for key in (
            "upload_weekday",
            "upload_time",
            "instagram_weekdays",
            "instagram_times",
            "fixed_hashtags",
        )
    }
    again = client.put("/api/social/settings", json=instagram_only, headers=staff)
    assert again.json() == changed


@pytest.mark.parametrize(
    "change",
    [
        {"tiktok_weekdays": []},
        {"tiktok_times": []},
        {"tiktok_times": ["10:00", "12:00", "17:00"]},
        {"slideshow_weekday": 4, "slideshow_time": None},
        {"slideshow_cutoff_weekday": 7, "slideshow_cutoff_time": "12:00"},
    ],
)
def test_wrong_tiktok_settings_are_refused(client: TestClient, change: dict):
    staff = ready_to_work(client, "superuser")
    found = client.get("/api/social/settings", headers=staff).json()

    response = client.put("/api/social/settings", json=found | change, headers=staff)

    assert response.status_code == 422
