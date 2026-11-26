"""Also on TikTok (spec #145, #147), against testing.FakeTikTok."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from pmp_backend.models import TikTokPost, WeeklyMedium
from pmp_backend.services import tiktok_posts
from pmp_backend.settings import Settings
from pmp_backend.testing import FakeLLM, FakeTikTok
from tests.test_scheduled_posts import Teams, act, make_suggestions
from tests.test_weekly_video import clip

BRUSSELS = ZoneInfo("Europe/Brussels")
ONLY_ME = {"also_on_tiktok": True, "privacy_level": "SELF_ONLY"}


def with_video(client, llm, settings, tmp_path, teams=None, title="Alpha"):
    """A Project whose week has a photo and a video; its suggestion's id."""
    teams = teams or Teams(client)
    teams.project(title)
    teams.week(title)
    response = client.post(
        "/api/my-weekly-update/video",
        files={"video": ("clip.mp4", clip(tmp_path), "video/mp4")},
        data={"consent": "true"},
        headers=teams.members[title],
    )
    assert response.status_code == 200, response.text
    mine = client.get("/api/my-weekly-update", headers=teams.members[title]).json()
    [suggestion_id] = make_suggestions(
        client, llm, settings, teams.staff, mine["current"]["closes_at"]
    )[title]
    return teams, suggestion_id


def connect(client: TestClient, staff: dict) -> None:
    response = client.post(
        "/api/social/tiktok/connect", json={"pasted": "a-code"}, headers=staff
    )
    assert response.status_code == 200, response.text


def post(client, staff, suggestion_id, body=None):
    return client.post(
        f"/api/post-suggestions/{suggestion_id}/post", json=body, headers=staff
    )


def one(client, staff, suggestion_id) -> dict:
    return next(
        s
        for s in client.get("/api/post-suggestions", headers=staff).json()
        if s["id"] == suggestion_id
    )


def publish(client, tiktok, settings, moment) -> list[int]:
    with client.app.state.sessionmaker() as session:
        return tiktok_posts.publish_due(session, tiktok, settings, moment)


def tiktok_time(found: dict) -> datetime:
    return datetime.fromisoformat(found["tiktok"]["scheduled_for"])


def test_the_tick_also_puts_the_video_in_tiktoks_line(
    client: TestClient, llm: FakeLLM, settings: Settings, tmp_path
):
    teams, suggestion_id = with_video(client, llm, settings, tmp_path)
    assert one(client, teams.staff, suggestion_id)["has_video"] is True

    response = post(client, teams.staff, suggestion_id, ONLY_ME)

    assert response.status_code == 200, response.text
    found = response.json()
    assert found["state"] == "scheduled"
    assert found["tiktok"]["state"] == "scheduled"
    assert found["tiktok"]["privacy_level"] == "SELF_ONLY"
    assert found["tiktok"]["allow_comment"] is True
    assert found["tiktok"]["allow_duet"] is found["tiktok"]["allow_stitch"] is False
    moment = tiktok_time(found).astimezone(BRUSSELS)
    assert (moment.hour, moment.minute) == (17, 0) and moment.weekday() < 5
    body = client.get("/api/scheduled-posts", headers=teams.staff).json()
    assert [s["id"] for s in body["tiktok_scheduled"]] == [suggestion_id]
    assert [s["id"] for s in body["scheduled"]] == [suggestion_id]
    mine = client.get("/api/my-weekly-update", headers=teams.members["Alpha"]).json()
    assert mine["current"]["tiktok_state"] == "scheduled"


def test_without_the_tick_nothing_goes_to_tiktok(
    client: TestClient, llm: FakeLLM, settings: Settings, tmp_path
):
    teams, suggestion_id = with_video(client, llm, settings, tmp_path)

    found = post(client, teams.staff, suggestion_id).json()

    assert found["state"] == "scheduled" and found["tiktok"] is None


def test_the_tick_needs_a_video_and_a_privacy_choice(
    client: TestClient, llm: FakeLLM, settings: Settings, tmp_path
):
    teams, with_clip = with_video(client, llm, settings, tmp_path)
    teams.project("Beta")
    closes = teams.week("Beta")
    [photo_only] = make_suggestions(client, llm, settings, teams.staff, closes)["Beta"]
    assert one(client, teams.staff, photo_only)["has_video"] is False

    no_choice = post(client, teams.staff, with_clip, {"also_on_tiktok": True})
    no_video = post(client, teams.staff, photo_only, ONLY_ME)

    assert no_choice.status_code == 422
    assert no_choice.json()["detail"] == "Choose who can see the video on TikTok."
    assert no_video.status_code == 409
    # Nothing was Posted.
    assert one(client, teams.staff, with_clip)["state"] == "waiting"
    assert one(client, teams.staff, photo_only)["state"] == "waiting"


def test_the_video_is_published_at_its_posting_time(
    client: TestClient,
    llm: FakeLLM,
    tiktok: FakeTikTok,
    settings: Settings,
    tmp_path,
):
    teams, suggestion_id = with_video(client, llm, settings, tmp_path)
    connect(client, teams.staff)
    before = post(client, teams.staff, suggestion_id, ONLY_ME).json()
    moment = tiktok_time(before)

    assert publish(client, tiktok, settings, moment - timedelta(minutes=1)) == []
    assert publish(client, tiktok, settings, moment) == [suggestion_id]

    [sent] = tiktok.posts
    assert sent.token == "access-1"
    assert sent.video.endswith(".mp4")
    assert sent.post.privacy_level == "SELF_ONLY"
    # Like Copy caption: the title as the first line.
    assert sent.post.caption == f"{before['title']}\n\n{before['caption']}"
    found = one(client, teams.staff, suggestion_id)
    assert found["tiktok"]["state"] == "published"
    assert found["tiktok"]["posted_at"] is not None
    # The Instagram post is untouched.
    assert found["state"] == "scheduled"
    with client.app.state.sessionmaker() as session:
        post_row = session.query(TikTokPost).one()
        assert session.get(WeeklyMedium, post_row.medium_id).posted is True
    body = client.get("/api/scheduled-posts", headers=teams.staff).json()
    assert [s["id"] for s in body["tiktok_published"]] == [suggestion_id]
    mine = client.get("/api/my-weekly-update", headers=teams.members["Alpha"]).json()
    assert mine["current"]["tiktok_state"] == "published"


def test_without_a_connection_it_goes_to_post_today(
    client: TestClient,
    llm: FakeLLM,
    tiktok: FakeTikTok,
    settings: Settings,
    tmp_path,
):
    teams, suggestion_id = with_video(client, llm, settings, tmp_path)
    moment = tiktok_time(post(client, teams.staff, suggestion_id, ONLY_ME).json())

    publish(client, tiktok, settings, moment)

    body = client.get("/api/scheduled-posts", headers=teams.staff).json()
    assert body["tiktok_automatic"] is False
    [waiting] = body["tiktok_to_post"]
    assert waiting["tiktok"]["error"] == tiktok_posts.NOT_CONNECTED
    assert waiting["tiktok"]["medium_id"] is not None
    assert tiktok.posts == []

    done = act(client, teams.staff, suggestion_id, "tiktok/posted")

    assert done.status_code == 200, done.text
    assert done.json()["tiktok"]["state"] == "posted_by_hand"
    assert done.json()["tiktok"]["posted_by"] == "Superuser Account"
    assert act(client, teams.staff, suggestion_id, "tiktok/posted").status_code == 409


def test_a_failure_is_tried_once_more_then_posted_by_hand(
    client: TestClient,
    llm: FakeLLM,
    tiktok: FakeTikTok,
    settings: Settings,
    tmp_path,
):
    teams, suggestion_id = with_video(client, llm, settings, tmp_path)
    connect(client, teams.staff)
    moment = tiktok_time(post(client, teams.staff, suggestion_id, ONLY_ME).json())
    tiktok.publish_failures = 2

    assert publish(client, tiktok, settings, moment) == []
    first = one(client, teams.staff, suggestion_id)["tiktok"]
    assert (first["state"], first["error"]) == (
        "scheduled",
        "TikTok answered 500: Fake failure",
    )
    assert publish(client, tiktok, settings, moment + timedelta(minutes=5)) == []
    assert publish(client, tiktok, settings, moment + timedelta(minutes=10)) == []

    found = one(client, teams.staff, suggestion_id)["tiktok"]
    assert found["state"] == "to_post_by_hand"
    assert found["error"].startswith("Publishing on TikTok failed:")


def test_a_privacy_level_tiktok_no_longer_allows_goes_to_post_today(
    client: TestClient,
    llm: FakeLLM,
    tiktok: FakeTikTok,
    settings: Settings,
    tmp_path,
):
    teams, suggestion_id = with_video(client, llm, settings, tmp_path)
    connect(client, teams.staff)
    body = ONLY_ME | {"privacy_level": "PUBLIC_TO_EVERYONE"}
    moment = tiktok_time(post(client, teams.staff, suggestion_id, body).json())

    publish(client, tiktok, settings, moment)

    found = one(client, teams.staff, suggestion_id)["tiktok"]
    assert found["state"] == "to_post_by_hand"
    assert (
        found["error"] == 'TikTok doesn\'t allow "Everyone" for this account right now.'
    )
    assert tiktok.posts == []


def test_each_channel_is_pulled_back_on_its_own(
    client: TestClient, llm: FakeLLM, settings: Settings, tmp_path
):
    teams, suggestion_id = with_video(client, llm, settings, tmp_path)
    post(client, teams.staff, suggestion_id, ONLY_ME)

    # Instagram back to Review: the TikTok video stays in its line.
    back = act(client, teams.staff, suggestion_id, "pull-back").json()
    assert back["state"] == "waiting" and back["tiktok"]["state"] == "scheduled"
    # Posting again keeps the TikTok post as it is.
    again = post(client, teams.staff, suggestion_id, ONLY_ME).json()
    assert again["state"] == "scheduled" and again["tiktok"]["state"] == "scheduled"

    gone = act(client, teams.staff, suggestion_id, "tiktok/pull-back")

    assert gone.status_code == 200, gone.text
    assert gone.json()["tiktok"] is None and gone.json()["state"] == "scheduled"
    assert (
        act(client, teams.staff, suggestion_id, "tiktok/pull-back").status_code == 404
    )


def test_tiktoks_line_never_has_the_same_project_twice_in_a_row(
    client: TestClient, llm: FakeLLM, settings: Settings, tmp_path
):
    teams, alpha = with_video(client, llm, settings, tmp_path)
    teams, beta = with_video(client, llm, settings, tmp_path, teams, "Beta")

    first = tiktok_time(post(client, teams.staff, alpha, ONLY_ME).json())
    second = tiktok_time(post(client, teams.staff, beta, ONLY_ME).json())

    # One video per Posting time: Beta gets the next weekday's 17:00.
    assert second > first
    assert second.astimezone(BRUSSELS).hour == 17


def test_creator_info_offers_the_accounts_choices(
    client: TestClient, tiktok: FakeTikTok
):
    teams = Teams(client)

    before = client.get("/api/social/tiktok/creator-info", headers=teams.staff).json()
    connect(client, teams.staff)
    after = client.get("/api/social/tiktok/creator-info", headers=teams.staff).json()
    tiktok.failing = True
    down = client.get("/api/social/tiktok/creator-info", headers=teams.staff).json()

    assert before["connected"] is False and len(before["privacy_levels"]) == 4
    assert after["connected"] is True
    assert after["privacy_levels"] == {"SELF_ONLY": "Only me"}
    assert after["nickname"] == "VIVES test"
    assert down["connected"] is False and down["error"]
