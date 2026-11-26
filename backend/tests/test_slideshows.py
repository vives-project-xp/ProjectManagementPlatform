"""The Weekly slideshow is put together at the cut-off and reviewed (spec #145,
#149)."""

from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from pmp_backend.services import slideshows, suggestions
from pmp_backend.settings import Settings
from pmp_backend.testing import FakeLLM
from tests.test_scheduled_posts import Teams, act, make_suggestions
from tests.test_weekly_photos import jpeg, scene
from tests.test_weekly_photos import upload as upload_photo


def week_with(client, llm, settings, photos: dict[str, int]):
    """Projects with that many photos each; their suggestion ids and the
    moment just after the week's Slideshow cut-off."""
    teams = Teams(client)
    closes = None
    seed = 1
    for title, count in photos.items():
        teams.project(title)
        for _ in range(count):
            upload_photo(client, teams.members[title], jpeg(scene(seed=seed)))
            seed += 1
        mine = client.get("/api/my-weekly-update", headers=teams.members[title])
        closes = mine.json()["current"]["closes_at"]
    found = make_suggestions(client, llm, settings, teams.staff, closes)
    made = suggestions.generate_at(datetime.fromisoformat(closes))
    # Saturday 07:00 after the suggestions: the Friday 12:00 cut-off is past.
    return teams, {t: ids[0] for t, ids in found.items()}, made + timedelta(days=3)


def build(client, moment) -> int | None:
    with client.app.state.sessionmaker() as session:
        return slideshows.build_due(session, moment)


def run(client, llm, moment) -> None:
    with client.app.state.sessionmaker() as session:
        slideshows.run_once(session, llm, moment)


def latest(client, staff) -> dict | None:
    response = client.get("/api/slideshows/latest", headers=staff)
    assert response.status_code == 200, response.text
    return response.json()


def chosen_of(client, staff, suggestion_id) -> int:
    found = client.get("/api/post-suggestions", headers=staff).json()
    return next(s for s in found if s["id"] == suggestion_id)["chosen"]["id"]


def test_one_photo_per_posted_project_then_more_until_four(
    client: TestClient, llm: FakeLLM, settings: Settings
):
    teams, ids, after = week_with(
        client, llm, settings, {"Alpha": 3, "Bravo": 1, "Charlie": 2}
    )
    for title in ("Bravo", "Alpha"):
        act(client, teams.staff, ids[title], "post")
    # Charlie is waiting for Review: not in the slideshow.

    assert build(client, after) is not None

    found = latest(client, teams.staff)
    assert found["state"] == "generating"
    order = [p["project"]["title"] for p in found["photos"]]
    # One each in the order they were Posted, then Alpha's other photos.
    assert order == ["Bravo", "Alpha", "Alpha", "Alpha"]
    alpha = [
        p["medium"]["id"] for p in found["photos"] if p["project"]["title"] == "Alpha"
    ]
    assert len(set(alpha)) == 3
    # Alpha's first photo is not its Instagram one; that one comes last.
    instagram = chosen_of(client, teams.staff, ids["Alpha"])
    assert alpha[0] != instagram and alpha[-1] == instagram
    # Bravo has one photo: the same as on Instagram.
    assert found["photos"][0]["medium"]["id"] == chosen_of(
        client, teams.staff, ids["Bravo"]
    )
    assert [p["project"]["title"] for p in found["projects"]] == ["Bravo", "Alpha"]


def test_many_projects_give_one_photo_each(
    client: TestClient, llm: FakeLLM, settings: Settings
):
    titles = ["Alpha", "Bravo", "Charlie", "Delta", "Echo"]
    teams, ids, after = week_with(client, llm, settings, dict.fromkeys(titles, 2))
    for title in titles:
        act(client, teams.staff, ids[title], "post")

    build(client, after)

    found = latest(client, teams.staff)
    assert sorted(p["project"]["title"] for p in found["photos"]) == titles


def test_fewer_photos_go_with_what_there_is_and_none_without(
    client: TestClient, llm: FakeLLM, settings: Settings
):
    teams, ids, after = week_with(client, llm, settings, {"Alpha": 1, "Bravo": 1})

    # Nothing Posted yet: no slideshow this week.
    build(client, after)
    assert latest(client, teams.staff)["state"] == "none"
    assert latest(client, teams.staff)["photos"] == []
    # Built once: the next round doesn't build it again.
    assert build(client, after + timedelta(hours=1)) is None

    # Generate again takes in what was Posted since.
    act(client, teams.staff, ids["Alpha"], "post")
    act(client, teams.staff, ids["Bravo"], "post")
    slideshow = latest(client, teams.staff)["id"]
    again = client.post(f"/api/slideshows/{slideshow}/generate", headers=teams.staff)

    assert again.status_code == 200, again.text
    assert len(again.json()["photos"]) == 2


def test_not_before_the_cut_off(client: TestClient, llm: FakeLLM, settings: Settings):
    teams, ids, after = week_with(client, llm, settings, {"Alpha": 1})
    act(client, teams.staff, ids["Alpha"], "post")

    # The Friday before the suggestions were made has passed, the next not yet.
    assert build(client, after - timedelta(days=1)) is None
    assert latest(client, teams.staff) is None


def test_the_ai_writes_the_text_from_the_titles(
    client: TestClient, llm: FakeLLM, settings: Settings
):
    teams, ids, after = week_with(client, llm, settings, {"Alpha": 2, "Bravo": 2})
    for title in ("Alpha", "Bravo"):
        act(client, teams.staff, ids[title], "post")
    asked = len(llm.requests)

    run(client, llm, after)

    found = latest(client, teams.staff)
    assert found["state"] == "waiting"
    assert found["title"] == "Deze week bij Elektronica-ICT 🔧"
    assert "#VIVEShogeschool" in found["caption"]
    [request] = llm.requests[asked:]
    assert "- Alpha\n- Bravo" in request.text
    assert request.media == []
    assert "member" not in request.text.lower()


def test_after_three_failures_staff_write_it_themselves(
    client: TestClient, llm: FakeLLM, settings: Settings
):
    teams, ids, after = week_with(client, llm, settings, {"Alpha": 1})
    act(client, teams.staff, ids["Alpha"], "post")
    llm.failing = True
    for minutes in (0, 20, 40):
        run(client, llm, after + timedelta(minutes=minutes))
    found = latest(client, teams.staff)
    assert found["state"] == "failed" and found["attempts"] == 3

    bad = client.put(
        f"/api/slideshows/{found['id']}",
        json={"title": "x" * 91, "caption": "Zonder hashtags"},
        headers=teams.staff,
    )
    good = client.put(
        f"/api/slideshows/{found['id']}",
        json={
            "title": "Projecten van deze week",
            "caption": "Kijk wat we bouwden! #VIVEShogeschool #ElektronicaICT #tech",
        },
        headers=teams.staff,
    )

    assert bad.status_code == 422
    assert "a title of 1-90 characters" in bad.json()["detail"]
    assert good.status_code == 200, good.text
    assert good.json()["state"] == "waiting"
    assert good.json()["reviewed_by"] == "Superuser Account"


def test_photos_are_swapped_removed_and_reordered(
    client: TestClient, llm: FakeLLM, settings: Settings
):
    teams, ids, after = week_with(client, llm, settings, {"Alpha": 2, "Bravo": 2})
    for title in ("Alpha", "Bravo"):
        act(client, teams.staff, ids[title], "post")
    run(client, llm, after)
    found = latest(client, teams.staff)
    alpha, bravo = (p["photos"] for p in found["projects"])
    url = f"/api/slideshows/{found['id']}/photos"

    # Bravo first, then Alpha's other photo; Alpha's first is out.
    changed = client.put(
        url, json={"medium_ids": [bravo[0]["id"], alpha[1]["id"]]}, headers=teams.staff
    )

    assert changed.status_code == 200, changed.text
    assert [p["medium"]["id"] for p in changed.json()["photos"]] == [
        bravo[0]["id"],
        alpha[1]["id"],
    ]
    twice = client.put(
        url, json={"medium_ids": [bravo[0]["id"]] * 2}, headers=teams.staff
    )
    empty = client.put(url, json={"medium_ids": []}, headers=teams.staff)
    stranger = client.put(url, json={"medium_ids": [999999]}, headers=teams.staff)
    assert (twice.status_code, empty.status_code, stranger.status_code) == (
        422,
        422,
        422,
    )


def test_refusing_means_no_slideshow_this_week(
    client: TestClient, llm: FakeLLM, settings: Settings
):
    teams, ids, after = week_with(client, llm, settings, {"Alpha": 1})
    act(client, teams.staff, ids["Alpha"], "post")
    run(client, llm, after)
    slideshow = latest(client, teams.staff)["id"]

    refused = client.post(
        f"/api/slideshows/{slideshow}/refuse",
        json={"reason": "Te weinig deze week."},
        headers=teams.staff,
    )

    assert refused.status_code == 200, refused.text
    assert refused.json()["state"] == "refused"
    assert refused.json()["refusal_reason"] == "Te weinig deze week."
    again = client.post(
        f"/api/slideshows/{slideshow}/refuse", headers=teams.staff, json={}
    )
    assert again.status_code == 409


def test_students_have_no_access(client: TestClient):
    teams = Teams(client)
    teams.project("Alpha")

    response = client.get("/api/slideshows/latest", headers=teams.members["Alpha"])

    assert response.status_code == 403
