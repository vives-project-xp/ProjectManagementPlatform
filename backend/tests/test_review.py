from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from pmp_backend.services import suggestions
from pmp_backend.settings import Settings
from pmp_backend.testing import FakeLLM
from tests.conftest import ready_to_work
from tests.test_post_suggestions import FIXED, listed, run_at
from tests.test_post_suggestions import week as week  # noqa: F401 (fixture)

GOOD = {
    "title": "Onze drone vliegt",
    "caption": f"Deze week testten we de motoren. {FIXED} #drone",
}


@pytest.fixture
def waiting(client: TestClient, llm: FakeLLM, settings: Settings, week):  # noqa: F811
    """Drone's suggestion, waiting for Review; Superuser headers and the media."""
    staff, project, closes, media = week
    run_at(client, llm, settings, suggestions.generate_at(closes))
    [found] = listed(client, staff)
    assert found["state"] == "waiting"
    return staff, found, media


def edit(client: TestClient, headers: dict, suggestion_id: int, **changes):
    return client.put(
        f"/api/post-suggestions/{suggestion_id}", json=GOOD | changes, headers=headers
    )


def test_a_reviewer_edits_the_text_and_picks_another_photo(client: TestClient, waiting):
    _, found, media = waiting
    teacher = ready_to_work(client, "teacher")
    other = next(m["id"] for m in media if m["id"] != found["chosen"]["id"])

    response = edit(client, teacher, found["id"], chosen_medium_id=other)

    assert response.status_code == 200, response.text
    changed = response.json()
    assert (changed["title"], changed["caption"]) == (GOOD["title"], GOOD["caption"])
    assert changed["chosen"]["id"] == other
    assert changed["state"] == "waiting"
    assert changed["reviewed_by"] == "Teacher Account"


@pytest.mark.parametrize(
    ("changes", "problem"),
    [
        ({"title": "x" * 81}, "a title of 1-80 characters"),
        ({"caption": "Zonder hashtags"}, "the fixed hashtags plus 1-3 others"),
        ({"title": "🎉🎉🎉 Feest"}, "at most 2 emoji"),
    ],
    ids=["long-title", "no-hashtags", "emoji"],
)
def test_edits_follow_the_same_rules_as_the_ai(
    client: TestClient, waiting, changes: dict, problem: str
):
    staff, found, _ = waiting
    response = edit(
        client, staff, found["id"], chosen_medium_id=found["chosen"]["id"], **changes
    )
    assert response.status_code == 422
    assert problem in response.json()["detail"]


def test_only_this_weeks_media_can_be_chosen(client: TestClient, waiting):
    staff, found, _ = waiting
    response = edit(client, staff, found["id"], chosen_medium_id=99999)
    assert response.status_code == 422
    assert "this week's photos" in response.json()["detail"]


def test_a_refusal_and_its_reason_reach_the_team(client: TestClient, waiting):
    staff, found, _ = waiting

    response = client.post(
        f"/api/post-suggestions/{found['id']}/refuse",
        json={"reason": "The photos are too dark this week."},
        headers=staff,
    )

    assert response.status_code == 200, response.text
    assert response.json()["state"] == "refused"
    student = ready_to_work(client, "student")
    assert client.get("/api/my-weekly-update", headers=student).json() is None
    # A Member of Drone sees it on their Weekly update.
    weeks = client.get(
        f"/api/projects/{found['project']['id']}/weekly-updates", headers=staff
    ).json()
    assert weeks[0]["suggestion_state"] == "refused"
    assert weeks[0]["refusal_reason"] == "The photos are too dark this week."
    # Refused means no post: it can't be edited any more.
    again = edit(client, staff, found["id"], chosen_medium_id=found["chosen"]["id"])
    assert again.status_code == 409


def test_generate_again_starts_over(client: TestClient, llm: FakeLLM, waiting):
    staff, found, _ = waiting
    client.post(f"/api/post-suggestions/{found['id']}/refuse", json={}, headers=staff)

    response = client.post(
        f"/api/post-suggestions/{found['id']}/generate", headers=staff
    )

    assert response.status_code == 200, response.text
    assert response.json()["state"] == "generating"
    # The test client returns after the background try.
    [again] = listed(client, staff)
    assert again["state"] == "waiting"
    assert again["refusal_reason"] is None
    assert len(llm.requests) == 2


def test_writing_it_yourself_when_the_ai_failed(
    client: TestClient,
    llm: FakeLLM,
    settings: Settings,
    week,  # noqa: F811
):
    staff, _, closes, media = week
    llm.failing = True
    moment = suggestions.generate_at(closes)
    for minutes in (0, 20, 40):
        run_at(client, llm, settings, moment + timedelta(minutes=minutes))
    [found] = listed(client, staff)
    assert found["state"] == "failed"

    response = edit(client, staff, found["id"], chosen_medium_id=media[0]["id"])

    assert response.status_code == 200, response.text
    written = response.json()
    assert written["state"] == "waiting"
    assert written["chosen"]["id"] == media[0]["id"]
    assert len(written["ranking"]) == len(media)


def test_only_my_projects(client: TestClient, waiting):
    staff, found, _ = waiting
    teacher = ready_to_work(client, "teacher")
    # The Teacher starting account is Drone's Product Owner; the Superuser isn't.
    mine = client.get("/api/post-suggestions?mine=true", headers=teacher).json()
    assert [s["id"] for s in mine] == [found["id"]]
    assert client.get("/api/post-suggestions?mine=true", headers=staff).json() == []


def test_students_cant_review(client: TestClient, waiting):
    _, found, _ = waiting
    student = ready_to_work(client, "student")
    assert edit(client, student, found["id"], chosen_medium_id=1).status_code == 403
    path = f"/api/post-suggestions/{found['id']}/refuse"
    assert client.post(path, json={}, headers=student).status_code == 403
    staff_path = "/api/post-suggestions/999/refuse"
    teacher = ready_to_work(client, "teacher")
    assert client.post(staff_path, json={}, headers=teacher).status_code == 404
