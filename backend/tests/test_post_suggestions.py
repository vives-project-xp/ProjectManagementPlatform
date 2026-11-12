import io
import json
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from pmp_backend.services import suggestions
from pmp_backend.services.post_ai import AiAnswer
from pmp_backend.settings import Settings
from pmp_backend.testing import FakeLLM
from tests.conftest import ready_to_work
from tests.test_weekly_photos import jpeg, scene
from tests.test_weekly_photos import upload as upload_photo
from tests.test_weekly_updates import WEDNESDAY_17, drone_team, set_settings
from tests.test_weekly_video import clip

FIXED = "#VIVEShogeschool #ElektronicaICT"


@pytest.fixture
def week(client: TestClient):
    """Drone's Weekly update with text and 4 photos of rising sharpness; its
    closing moment."""
    staff, project, lisa, tom = drone_team(client)
    set_settings(client, staff, WEDNESDAY_17)
    client.put(
        "/api/my-weekly-update",
        json={"text": "We tested the motors of the drone."},
        headers=lisa,
    )
    for seed in range(4):
        upload_photo(client, lisa, jpeg(scene(seed=seed)))
    current = client.get("/api/my-weekly-update", headers=lisa).json()["current"]
    closes = datetime.fromisoformat(current["closes_at"])
    return staff, project, closes, current["media"]


def run_at(client: TestClient, llm: FakeLLM, settings: Settings, moment: datetime):
    with client.app.state.sessionmaker() as session:
        suggestions.run_once(session, llm, settings.social_media_dir, moment)


def listed(client: TestClient, staff: dict) -> list[dict]:
    response = client.get("/api/post-suggestions", headers=staff)
    assert response.status_code == 200, response.text
    return response.json()


def test_made_at_seven_a_week_after_the_week_closed(
    client: TestClient, llm: FakeLLM, settings: Settings, week
):
    staff, project, closes, media = week
    moment = suggestions.generate_at(closes)
    assert (moment - closes).days == 6 and (moment.hour, moment.minute) == (7, 0)

    run_at(client, llm, settings, moment - timedelta(minutes=1))
    assert listed(client, staff) == []

    run_at(client, llm, settings, moment)

    [found] = listed(client, staff)
    assert found["project"] == {"id": project, "title": "Drone"}
    assert found["state"] == "waiting"
    assert found["title"] == "Onze drone zweeft! 🚁"
    assert FIXED in found["caption"]
    assert found["chosen"]["id"] == found["ranking"][0]["id"]
    assert sorted(m["id"] for m in found["ranking"]) == sorted(m["id"] for m in media)
    assert found["why"]


def test_the_ai_gets_only_the_fixed_inputs(
    client: TestClient, llm: FakeLLM, settings: Settings, week
):
    staff, _, closes, _ = week
    run_at(client, llm, settings, suggestions.generate_at(closes))

    [request] = llm.requests
    everything = request.instructions + request.text
    assert "Drone" in request.text
    assert "We tested the motors of the drone." in request.text
    assert FIXED in request.instructions
    # No names or emails of the team or its Product Owner.
    for private in ("Lisa", "Tom", "Peeters", "Teacher Account", "@"):
        assert private not in everything.replace(FIXED, "")
    # The 3 best of 4 photos, small enough for the endpoint.
    assert [m.kind for m in request.media] == ["photo"] * 3
    for medium in request.media:
        assert max(Image.open(io.BytesIO(medium.data)).size) <= 1600
    assert request.schema["properties"]["chosen"]["enum"] == [
        m.label for m in request.media
    ]


def test_a_rule_breaking_answer_is_tried_again_then_fails(
    client: TestClient, llm: FakeLLM, settings: Settings, week
):
    staff, _, closes, _ = week
    moment = suggestions.generate_at(closes)
    too_long = json.dumps(
        {
            "title": "x" * 81,
            "caption": f"Hoi {FIXED} #drone",
            "chosen": "photo-1",
            "ranking": [],
            "why": "",
        }
    )
    llm.answers = [too_long, "not json", AiAnswer(None, "length")]

    run_at(client, llm, settings, moment)
    [found] = listed(client, staff)
    assert (found["state"], found["attempts"]) == ("generating", 1)
    assert "title of 1-80 characters" in found["last_error"]

    # Not again before the 20 minutes are up.
    run_at(client, llm, settings, moment + timedelta(minutes=10))
    assert len(llm.requests) == 1
    run_at(client, llm, settings, moment + timedelta(minutes=20))
    run_at(client, llm, settings, moment + timedelta(minutes=40))

    [found] = listed(client, staff)
    assert (found["state"], found["attempts"]) == ("failed", 3)
    assert "stopped early" in found["last_error"]


def test_the_ai_being_down_counts_as_a_failed_try(
    client: TestClient, llm: FakeLLM, settings: Settings, week
):
    staff, _, closes, _ = week
    llm.failing = True
    run_at(client, llm, settings, suggestions.generate_at(closes))

    [found] = listed(client, staff)
    assert found["state"] == "generating"
    assert found["last_error"] == "The AI can't be reached right now."


@pytest.mark.parametrize(
    "answer",
    [
        {"caption": "Zonder vaste hashtags #drone"},
        {"caption": f"Te veel {FIXED} #a #b #c #d"},
        {"title": "😀😀😀 drie emoji"},
    ],
    ids=["no-fixed-hashtags", "too-many-hashtags", "too-many-emoji"],
)
def test_answers_are_checked(
    client: TestClient, llm: FakeLLM, settings: Settings, week, answer: dict
):
    staff, _, closes, media = week
    labels = [f"photo-{m['id']}" for m in media]
    good = {
        "title": "Titel",
        "caption": f"Tekst {FIXED} #drone",
        "chosen": labels[0],
        "ranking": labels,
        "why": "Because.",
    }
    llm.answers = [json.dumps(good | answer)]

    run_at(client, llm, settings, suggestions.generate_at(closes))

    assert listed(client, staff)[0]["state"] == "generating"


def test_no_suggestion_without_media_or_for_archived_projects(
    client: TestClient, llm: FakeLLM, settings: Settings
):
    staff, project, lisa, _ = drone_team(client)
    set_settings(client, staff, WEDNESDAY_17)
    client.put("/api/my-weekly-update", json={"text": "Only text."}, headers=lisa)
    closes = datetime.fromisoformat(
        client.get("/api/my-weekly-update", headers=lisa).json()["current"]["closes_at"]
    )

    run_at(client, llm, settings, suggestions.generate_at(closes))
    assert listed(client, staff) == []

    upload_photo(client, lisa)
    client.post(f"/api/projects/{project}/archive", headers=staff)
    run_at(client, llm, settings, suggestions.generate_at(closes))
    assert listed(client, staff) == []
    assert llm.requests == []


def test_only_staff_see_the_suggestions(client: TestClient, week):
    _, _, _, _ = week
    teacher = ready_to_work(client, "teacher")
    assert client.get("/api/post-suggestions", headers=teacher).status_code == 200
    student = ready_to_work(client, "student")
    assert client.get("/api/post-suggestions", headers=student).status_code == 403


def test_the_superuser_sees_whether_the_ai_is_configured(client: TestClient):
    staff = ready_to_work(client, "superuser")
    found = client.get("/api/social/status", headers=staff).json()
    assert found == {"ai_configured": False}


def test_the_ai_also_gets_the_video(
    client: TestClient, llm: FakeLLM, settings: Settings, tmp_path
):
    staff, _, lisa, _ = drone_team(client)
    set_settings(client, staff, WEDNESDAY_17)
    upload_photo(client, lisa)
    client.post(
        "/api/my-weekly-update/video",
        files={"video": ("clip.mp4", clip(tmp_path), "video/mp4")},
        data={"consent": "true"},
        headers=lisa,
    )
    closes = datetime.fromisoformat(
        client.get("/api/my-weekly-update", headers=lisa).json()["current"]["closes_at"]
    )

    run_at(client, llm, settings, suggestions.generate_at(closes))

    [request] = llm.requests
    assert [m.kind for m in request.media] == ["photo", "video"]
    # The small copy for the AI, not the posted one.
    assert request.media[1].data[4:8] == b"ftyp"
    assert listed(client, staff)[0]["state"] == "waiting"
