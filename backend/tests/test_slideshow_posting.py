"""Posting the Weekly slideshow: its Posting time, the TikTok inbox, the Song
check and To post today (spec #145, #150)."""

import io
import zipfile
from datetime import datetime, timedelta
from urllib.parse import urlparse

import pytest
from fastapi.testclient import TestClient

from pmp_backend.app import create_app
from pmp_backend.models import WeeklyMedium, WeeklySlideshow, WeeklySlideshowPhoto
from pmp_backend.services import slideshows
from pmp_backend.settings import Settings
from pmp_backend.testing import FakeLLM, FakeTikTok
from tests.test_scheduled_posts import act
from tests.test_slideshows import latest, run, week_with

BRUSSELS = slideshows.BRUSSELS
PUBLIC = "https://pmp.example.org"


@pytest.fixture
def public(settings: Settings) -> Settings:
    return settings.model_copy(
        update={
            "public_media_url": PUBLIC,
            "tiktok_verification_file": "tiktokAbC123.txt",
            "tiktok_verification_content": "tiktok-developers-site-verification=AbC123",
        }
    )


def waiting_slideshow(client, llm, settings, photos=None) -> tuple:
    """A written slideshow waiting for Review; teams, its id, the cut-off."""
    teams, ids, after = week_with(client, llm, settings, photos or {"Alpha": 2})
    for suggestion_id in ids.values():
        act(client, teams.staff, suggestion_id, "post")
    run(client, llm, after)
    found = latest(client, teams.staff)
    assert found["state"] == "waiting"
    return teams, found["id"], after


def slideshow_act(client, staff, slideshow_id, action, body=None):
    return client.post(
        f"/api/slideshows/{slideshow_id}/{action}", json=body, headers=staff
    )


def send(client, tiktok, settings, moment) -> list[int]:
    with client.app.state.sessionmaker() as session:
        return slideshows.publish_due(session, tiktok, settings, moment)


def made_long_ago(client, slideshow_id) -> None:
    """As if it was put together 8 days ago: its Posting time has passed."""
    with client.app.state.sessionmaker() as session:
        slideshow = session.get(WeeklySlideshow, slideshow_id)
        slideshow.created_at = slideshow.created_at - timedelta(days=8)
        session.commit()


def test_posted_before_its_posting_time_it_waits_for_friday_18(
    client: TestClient, llm: FakeLLM, settings: Settings
):
    teams, slideshow, _ = waiting_slideshow(client, llm, settings)

    response = slideshow_act(client, teams.staff, slideshow, "post")

    assert response.status_code == 200, response.text
    found = response.json()
    assert found["state"] == "scheduled"
    moment = datetime.fromisoformat(found["scheduled_for"]).astimezone(BRUSSELS)
    assert (moment.weekday(), moment.hour, moment.minute) == (4, 18, 0)
    assert moment > datetime.now(BRUSSELS)
    lists = client.get("/api/slideshows", headers=teams.staff).json()
    assert [s["id"] for s in lists["scheduled"]] == [slideshow]

    back = slideshow_act(client, teams.staff, slideshow, "pull-back")
    assert back.json()["state"] == "waiting" and back.json()["scheduled_for"] is None


def test_posted_late_it_goes_out_at_once_and_by_hand_without_tiktok(
    client: TestClient, llm: FakeLLM, tiktok: FakeTikTok, settings: Settings
):
    teams, slideshow, _ = waiting_slideshow(client, llm, settings)
    made_long_ago(client, slideshow)

    found = slideshow_act(client, teams.staff, slideshow, "post").json()
    moment = datetime.fromisoformat(found["scheduled_for"])
    assert moment <= datetime.now(BRUSSELS) + timedelta(seconds=5)
    send(client, tiktok, settings, moment + timedelta(seconds=1))

    found = latest(client, teams.staff)
    assert found["state"] == "to_post_by_hand"
    assert found["publish_error"] == slideshows.NOT_AUTOMATIC
    assert tiktok.inbox == []
    lists = client.get("/api/slideshows", headers=teams.staff).json()
    assert [s["id"] for s in lists["to_finish"]] == [slideshow]


def test_posted_needs_the_song_check_and_keeps_the_photos(
    client: TestClient, llm: FakeLLM, tiktok: FakeTikTok, settings: Settings
):
    teams, slideshow, _ = waiting_slideshow(client, llm, settings)
    made_long_ago(client, slideshow)
    found = slideshow_act(client, teams.staff, slideshow, "post").json()
    send(client, tiktok, settings, datetime.fromisoformat(found["scheduled_for"]))

    without = slideshow_act(client, teams.staff, slideshow, "posted", {})
    done = slideshow_act(
        client, teams.staff, slideshow, "posted", {"song_checked": True}
    )

    assert without.status_code == 422
    assert without.json()["detail"] == slideshows.NEEDS_SONG_CHECK
    assert done.status_code == 200, done.text
    assert done.json()["state"] == "posted"
    assert done.json()["posted_by"] == "Superuser Account"
    with client.app.state.sessionmaker() as session:
        ids = [
            p.medium_id
            for p in session.query(WeeklySlideshowPhoto).filter_by(
                slideshow_id=slideshow
            )
        ]
        assert all(session.get(WeeklyMedium, i).posted for i in ids)
    mine = client.get("/api/my-weekly-update", headers=teams.members["Alpha"]).json()
    assert mine["current"]["slideshow_at"] == found["scheduled_for"]


def connect(client, staff) -> None:
    response = client.post(
        "/api/social/tiktok/connect", json={"pasted": "a-code"}, headers=staff
    )
    assert response.status_code == 200, response.text


def test_with_a_public_address_it_goes_to_the_tiktok_inbox(
    client: TestClient,
    llm: FakeLLM,
    tiktok: FakeTikTok,
    settings: Settings,
    public: Settings,
):
    teams, slideshow, _ = waiting_slideshow(client, llm, settings)
    connect(client, teams.staff)
    made_long_ago(client, slideshow)
    found = slideshow_act(client, teams.staff, slideshow, "post").json()
    outside = TestClient(create_app(public))
    fetched = []
    tiktok.fetch = lambda url: fetched.append(
        outside.get(urlparse(url).path).headers["content-type"]
    )

    sent = send(client, tiktok, public, datetime.fromisoformat(found["scheduled_for"]))

    assert sent == [slideshow]
    [(urls, title, caption)] = tiktok.inbox
    assert len(urls) == len(found["photos"]) == 2
    assert all(url.startswith(f"{PUBLIC}/social/") for url in urls)
    assert fetched == ["image/jpeg", "image/jpeg"]
    assert (title, caption) == (found["title"], found["caption"])
    # Once in the inbox the links find nothing.
    assert outside.get(urlparse(urls[0]).path).status_code == 404
    now = latest(client, teams.staff)
    assert now["state"] == "in_inbox"


def test_a_failed_send_is_tried_once_more_then_by_hand(
    client: TestClient,
    llm: FakeLLM,
    tiktok: FakeTikTok,
    settings: Settings,
    public: Settings,
):
    teams, slideshow, _ = waiting_slideshow(client, llm, settings)
    connect(client, teams.staff)
    made_long_ago(client, slideshow)
    found = slideshow_act(client, teams.staff, slideshow, "post").json()
    moment = datetime.fromisoformat(found["scheduled_for"])
    tiktok.publish_failures = 2

    send(client, tiktok, public, moment)
    first = latest(client, teams.staff)
    send(client, tiktok, public, moment + timedelta(minutes=10))

    assert first["state"] == "scheduled"
    assert first["publish_error"] == "TikTok answered 500: Fake failure"
    found = latest(client, teams.staff)
    assert found["state"] == "to_post_by_hand"
    assert found["publish_error"].startswith("Sending to TikTok failed:")


def test_not_posted_by_the_next_cut_off_it_is_dropped(
    client: TestClient, llm: FakeLLM, settings: Settings
):
    teams, ids, after = week_with(client, llm, settings, {"Alpha": 1})
    act(client, teams.staff, ids["Alpha"], "post")
    with client.app.state.sessionmaker() as session:
        # Last week's slideshow, never Posted.
        old = WeeklySlideshow(
            closes_at=datetime(2026, 1, 7, 17, tzinfo=BRUSSELS), state="waiting"
        )
        session.add(old)
        session.commit()
        old_id = old.id

    run(client, llm, after)

    with client.app.state.sessionmaker() as session:
        dropped = session.get(WeeklySlideshow, old_id)
        assert dropped.state == "dropped"
        assert dropped.publish_error == slideshows.NOT_IN_TIME
    assert latest(client, teams.staff)["state"] == "waiting"


def test_the_photos_come_as_one_zip_in_order(
    client: TestClient, llm: FakeLLM, settings: Settings
):
    teams, slideshow, _ = waiting_slideshow(
        client, llm, settings, {"Alpha": 1, "Bravo_Drone": 1}
    )

    response = client.get(
        f"/api/slideshows/{slideshow}/photos.zip", headers=teams.staff
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    names = zipfile.ZipFile(io.BytesIO(response.content)).namelist()
    assert names == ["01-alpha.jpg", "02-bravo-drone.jpg"]


def test_the_verification_file_is_served_at_the_public_address(public: Settings):
    outside = TestClient(create_app(public))

    response = outside.get("/social/tiktokAbC123.txt")

    assert response.status_code == 200
    assert response.text == "tiktok-developers-site-verification=AbC123"
    assert outside.get("/social/tiktokOther.txt").status_code == 404
