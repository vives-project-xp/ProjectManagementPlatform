"""Automatic publishing on Instagram (#117), against testing.FakeInstagram."""

from datetime import datetime, timedelta
from urllib.parse import urlparse

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from pmp_backend.app import create_app
from pmp_backend.models import ChannelToken, PostSuggestion, PublishLink, WeeklyMedium
from pmp_backend.services import posting, publishing, social
from pmp_backend.settings import Settings
from pmp_backend.testing import FakeInstagram, FakeLLM
from tests.test_scheduled_posts import Teams, act, make_suggestions, scheduled
from tests.test_weekly_video import clip

PUBLIC = "https://pmp.example.org"
TOKEN = SecretStr("first-token")


@pytest.fixture
def on_instagram(settings: Settings) -> Settings:
    """The settings with an Instagram token and a public address."""
    return settings.model_copy(
        update={"instagram_token": TOKEN, "public_media_url": PUBLIC}
    )


def one_scheduled_post(client, llm, settings) -> tuple[Teams, int, datetime]:
    """Alpha's photo post, Scheduled; its id and Posting time."""
    teams = Teams(client)
    teams.project("Alpha")
    closes = teams.week("Alpha")
    [suggestion_id] = make_suggestions(client, llm, settings, teams.staff, closes)[
        "Alpha"
    ]
    act(client, teams.staff, suggestion_id, "post")
    [(_, moment)] = scheduled(client, teams.staff)
    return teams, suggestion_id, moment


def run_at(client, instagram, settings, moment: datetime) -> list[int]:
    with client.app.state.sessionmaker() as session:
        return posting.run_once(session, moment, instagram, settings)


def suggestion(client: TestClient, suggestion_id: int) -> PostSuggestion:
    with client.app.state.sessionmaker() as session:
        found = session.get(PostSuggestion, suggestion_id)
        session.expunge(found)
        return found


def test_a_photo_post_is_published_through_a_publish_link(
    client: TestClient,
    llm: FakeLLM,
    instagram: FakeInstagram,
    settings: Settings,
    on_instagram: Settings,
):
    teams, suggestion_id, moment = one_scheduled_post(client, llm, settings)
    public = TestClient(create_app(on_instagram))
    fetched = []

    def fetch(url: str) -> None:
        # Instagram downloads the photo while the post is being published.
        response = public.get(urlparse(url).path)
        fetched.append((response.status_code, response.headers["content-type"]))

    instagram.fetch = fetch

    assert run_at(client, instagram, on_instagram, moment - timedelta(minutes=1)) == []
    assert run_at(client, instagram, on_instagram, moment) == [suggestion_id]

    [post] = instagram.posts
    assert post.kind == "photo"
    assert post.source.startswith(f"{PUBLIC}/social/")
    assert len(post.source.rsplit("/", 1)[1]) >= 32
    assert post.caption.startswith("Onze drone zweeft!")
    assert post.token == "first-token"
    assert fetched == [(200, "image/jpeg")]
    # Once published, the link finds nothing.
    assert public.get(urlparse(post.source).path).status_code == 404
    done = suggestion(client, suggestion_id)
    assert (done.state, done.published_url) == (
        "published",
        "https://www.instagram.com/p/fake1/",
    )
    with client.app.state.sessionmaker() as session:
        assert session.get(WeeklyMedium, done.chosen_medium_id).posted is True
    body = client.get("/api/scheduled-posts", headers=teams.staff).json()
    assert [p["published_url"] for p in body["published"]] == [done.published_url]
    assert body["published"][0]["posted_by"] is None
    mine = client.get("/api/my-weekly-update", headers=teams.members["Alpha"]).json()
    assert mine["current"]["published_url"] == done.published_url


def test_the_video_is_published_as_a_reel_without_a_public_address(
    client: TestClient,
    llm: FakeLLM,
    instagram: FakeInstagram,
    settings: Settings,
    tmp_path,
):
    teams = Teams(client)
    teams.project("Alpha")
    teams.week("Alpha")
    client.post(
        "/api/my-weekly-update/video",
        files={"video": ("clip.mp4", clip(tmp_path), "video/mp4")},
        data={"consent": "true"},
        headers=teams.members["Alpha"],
    )
    mine = client.get("/api/my-weekly-update", headers=teams.members["Alpha"]).json()
    video = next(m for m in mine["current"]["media"] if m["kind"] == "video")
    [suggestion_id] = make_suggestions(
        client, llm, settings, teams.staff, mine["current"]["closes_at"]
    )["Alpha"]
    found = suggestion(client, suggestion_id)
    client.put(
        f"/api/post-suggestions/{suggestion_id}",
        json={
            "title": found.title,
            "caption": found.caption,
            "chosen_medium_id": video["id"],
        },
        headers=teams.staff,
    )
    act(client, teams.staff, suggestion_id, "post")
    [(_, moment)] = scheduled(client, teams.staff)
    token_only = settings.model_copy(update={"instagram_token": TOKEN})

    assert run_at(client, instagram, token_only, moment) == [suggestion_id]

    [post] = instagram.posts
    assert post.kind == "reel"
    assert post.source.endswith(f"{video['id']}.mp4")


def test_a_photo_without_a_public_address_goes_to_post_today(
    client: TestClient, llm: FakeLLM, instagram: FakeInstagram, settings: Settings
):
    teams, suggestion_id, moment = one_scheduled_post(client, llm, settings)
    token_only = settings.model_copy(update={"instagram_token": TOKEN})

    assert run_at(client, instagram, token_only, moment) == []

    assert instagram.posts == []
    staff_view = TestClient(create_app(token_only))
    body = staff_view.get("/api/scheduled-posts", headers=teams.staff).json()
    [waiting] = body["to_post"]
    assert "reachable from the internet" in waiting["publish_error"]
    assert body["channel"]["automatic"] is True
    assert body["channel"]["photos_automatic"] is False


def test_a_failure_is_tried_once_more_ten_minutes_later(
    client: TestClient,
    llm: FakeLLM,
    instagram: FakeInstagram,
    settings: Settings,
    on_instagram: Settings,
):
    teams, suggestion_id, moment = one_scheduled_post(client, llm, settings)
    instagram.failures = 2

    run_at(client, instagram, on_instagram, moment)
    first = suggestion(client, suggestion_id)
    assert (first.state, first.publish_attempts) == ("scheduled", 1)
    assert first.publish_retry_at == moment + timedelta(minutes=10)
    assert run_at(client, instagram, on_instagram, moment + timedelta(minutes=5)) == []
    assert instagram.failures == 1

    run_at(client, instagram, on_instagram, moment + timedelta(minutes=10))

    body = client.get("/api/scheduled-posts", headers=teams.staff).json()
    [waiting] = body["to_post"]
    assert waiting["id"] == suggestion_id
    assert waiting["publish_error"].startswith("Publishing on Instagram failed")
    assert instagram.posts == []


def test_the_retry_can_succeed(
    client: TestClient,
    llm: FakeLLM,
    instagram: FakeInstagram,
    settings: Settings,
    on_instagram: Settings,
):
    _, suggestion_id, moment = one_scheduled_post(client, llm, settings)
    instagram.failures = 1

    run_at(client, instagram, on_instagram, moment)
    assert run_at(client, instagram, on_instagram, moment + timedelta(minutes=10)) == [
        suggestion_id
    ]

    assert suggestion(client, suggestion_id).state == "published"


def test_a_pulled_back_post_is_never_published(
    client: TestClient,
    llm: FakeLLM,
    instagram: FakeInstagram,
    settings: Settings,
    on_instagram: Settings,
):
    teams, suggestion_id, moment = one_scheduled_post(client, llm, settings)
    act(client, teams.staff, suggestion_id, "pull-back")

    assert run_at(client, instagram, on_instagram, moment) == []
    assert instagram.posts == []


def test_without_a_token_posts_go_to_post_today_as_before(
    client: TestClient, llm: FakeLLM, instagram: FakeInstagram, settings: Settings
):
    teams, suggestion_id, moment = one_scheduled_post(client, llm, settings)

    run_at(client, instagram, settings, moment)

    assert instagram.posts == []
    body = client.get("/api/scheduled-posts", headers=teams.staff).json()
    assert [p["id"] for p in body["to_post"]] == [suggestion_id]
    assert body["to_post"][0]["publish_error"] is None
    assert body["channel"]["automatic"] is False


def test_publish_links_expire_and_unknown_codes_find_nothing(
    client: TestClient, llm: FakeLLM, settings: Settings, on_instagram: Settings
):
    teams, suggestion_id, moment = one_scheduled_post(client, llm, settings)
    public = TestClient(create_app(on_instagram))
    with client.app.state.sessionmaker() as session:
        found = session.get(PostSuggestion, suggestion_id)
        medium = session.get(WeeklyMedium, found.chosen_medium_id)
        now = datetime.now().astimezone()
        fresh = publishing.create_link(session, found, medium, now)
        old = publishing.create_link(session, found, medium, now - timedelta(hours=2))
        session.commit()
        fresh_code, old_code = fresh.code, old.code

    assert public.get(f"/social/{fresh_code}").status_code == 200
    assert public.get(f"/social/{old_code}").status_code == 404
    assert public.get("/social/" + "x" * 32).status_code == 404
    assert public.get("/social/short").status_code == 404
    # Without PUBLIC_MEDIA_URL the route doesn't exist at all.
    assert client.get(f"/social/{fresh_code}").status_code == 404

    # The daily clean-up removes expired links.
    with client.app.state.sessionmaker() as session:
        social.clean_up(session, settings.social_media_dir, now)
        assert session.get(PublishLink, old_code) is None
        assert session.get(PublishLink, fresh_code) is not None


def test_the_token_is_refreshed_before_it_expires_and_never_shown(
    client: TestClient,
    instagram: FakeInstagram,
    on_instagram: Settings,
):
    staff = Teams(client).staff
    now = datetime.now().astimezone()
    with client.app.state.sessionmaker() as session:
        # Its expiry is unknown at first, so it is refreshed to learn it.
        assert publishing.refresh_token(session, instagram, on_instagram, now)
        # Far from expiring: nothing to do.
        assert not publishing.refresh_token(
            session, instagram, on_instagram, now + timedelta(days=2)
        )
        # A week before it expires: refreshed again.
        assert publishing.refresh_token(
            session, instagram, on_instagram, now + timedelta(days=54)
        )
        row = session.get(ChannelToken, "instagram")
        assert row.token == "refreshed-2"
    assert instagram.refreshes == ["first-token", "refreshed-1"]

    response = client.get("/api/scheduled-posts", headers=staff)
    assert "refreshed-2" not in response.text
    assert "first-token" not in response.text


def test_a_failed_refresh_shows_a_notice(
    client: TestClient, instagram: FakeInstagram, on_instagram: Settings
):
    staff = Teams(client).staff
    instagram.refresh_failing = True
    now = datetime.now().astimezone()
    with client.app.state.sessionmaker() as session:
        assert not publishing.refresh_token(session, instagram, on_instagram, now)
        # Not tried again every minute.
        assert not publishing.refresh_token(
            session, instagram, on_instagram, now + timedelta(hours=1)
        )
    assert len(instagram.refreshes) == 1

    staff_view = TestClient(create_app(on_instagram))
    body = staff_view.get("/api/scheduled-posts", headers=staff).json()
    assert "Fake refresh failure" in body["channel"]["refresh_error"]


def test_a_token_that_never_expires_is_not_refreshed(
    client: TestClient, instagram: FakeInstagram, on_instagram: Settings
):
    """Unified login (graph.facebook.com): INSTAGRAM_REFRESH_URL empty."""
    unified = on_instagram.model_copy(
        update={
            "instagram_refresh_url": "",
            "instagram_api_url": "https://graph.facebook.com/v23.0",
        }
    )
    with client.app.state.sessionmaker() as session:
        assert not publishing.refresh_token(
            session, instagram, unified, datetime.now().astimezone()
        )
        assert publishing.status(session, unified).refresh_error is None
    assert instagram.refreshes == []
