"""The 4-month clean-up of never-posted Media and the outcome per week (#118)."""

from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from pmp_backend.models import WeeklyMedium
from pmp_backend.services import social
from pmp_backend.settings import Settings
from pmp_backend.testing import FakeLLM
from tests.test_scheduled_posts import act, close_week_of, scheduled, three_projects
from tests.test_weekly_photos import jpeg, scene
from tests.test_weekly_photos import upload as upload_photo
from tests.test_weekly_updates import WEDNESDAY_17, drone_team, set_settings


def mine(client: TestClient, headers: dict) -> dict:
    response = client.get("/api/my-weekly-update", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def clean_up_at(client: TestClient, settings: Settings, moment: datetime) -> list[int]:
    with client.app.state.sessionmaker() as session:
        return social.clean_up(session, settings.social_media_dir, moment)


def close_weeks(teams) -> None:
    """Make the Teams' open weeks earlier ones, as the team sees them."""
    for project in teams.ids.values():
        close_week_of(project)


def file_of(settings: Settings, project: int, medium_id: int):
    return settings.social_media_dir / str(project) / f"{medium_id}.jpg"


def test_never_posted_media_go_four_months_after_the_week(
    client: TestClient, settings: Settings
):
    staff, project, lisa, _ = drone_team(client)
    set_settings(client, staff, WEDNESDAY_17)
    client.put(
        "/api/my-weekly-update", json={"text": "We tested the motors."}, headers=lisa
    )
    for seed in (1, 2):
        upload_photo(client, lisa, jpeg(scene(seed=seed)))
    current = mine(client, lisa)["current"]
    closes = datetime.fromisoformat(current["closes_at"])
    posted, unposted = (medium["id"] for medium in current["media"])
    with client.app.state.sessionmaker() as session:
        session.get(WeeklyMedium, posted).posted = True
        session.commit()
    close_week_of(project)
    closes -= timedelta(days=7)

    # Not yet a day before the 4 months are over.
    assert clean_up_at(client, settings, closes + timedelta(days=121)) == []
    assert file_of(settings, project, unposted).is_file()

    assert len(clean_up_at(client, settings, closes + timedelta(days=123))) == 1

    assert not file_of(settings, project, unposted).exists()
    assert file_of(settings, project, posted).is_file()
    [week] = mine(client, lisa)["earlier"]
    assert week["text"] == "We tested the motors."
    assert [medium["id"] for medium in week["media"]] == [posted]
    assert week["media_removed_at"] is not None
    # Once is enough: nothing left to remove the next day.
    assert clean_up_at(client, settings, closes + timedelta(days=124)) == []


def test_a_post_still_on_its_way_keeps_its_media(
    client: TestClient, llm: FakeLLM, settings: Settings
):
    teams, found = three_projects(client, llm, settings)
    act(client, teams.staff, found["Alpha"][0], "post")
    [(_, moment)] = scheduled(client, teams.staff)

    close_weeks(teams)

    cleaned = clean_up_at(client, settings, moment + timedelta(days=200))

    # Bravo and Charlie were never posted; Alpha is still scheduled.
    assert len(cleaned) == 2
    alpha = mine(client, teams.members["Alpha"])["earlier"][0]
    assert alpha["media_removed_at"] is None
    assert len(alpha["media"]) == 1


def test_the_team_sees_each_weeks_outcome(
    client: TestClient, llm: FakeLLM, settings: Settings
):
    teams, found = three_projects(client, llm, settings)
    act(client, teams.staff, found["Alpha"][0], "post")
    [(_, moment)] = scheduled(client, teams.staff)
    client.post(
        f"/api/post-suggestions/{found['Bravo'][0]}/refuse",
        json={"reason": "Too dark this week."},
        headers=teams.staff,
    )
    close_weeks(teams)

    alpha = mine(client, teams.members["Alpha"])["earlier"][0]
    bravo = mine(client, teams.members["Bravo"])["earlier"][0]
    charlie = mine(client, teams.members["Charlie"])["earlier"][0]

    assert alpha["suggestion_state"] == "scheduled"
    assert datetime.fromisoformat(alpha["scheduled_for"]) == moment
    assert alpha["posted_at"] is None
    assert (bravo["suggestion_state"], bravo["refusal_reason"]) == (
        "refused",
        "Too dark this week.",
    )
    assert charlie["suggestion_state"] == "waiting"
