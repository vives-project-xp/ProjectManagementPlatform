from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from pmp_backend.models import WeeklyMedium
from pmp_backend.services import posting, suggestions
from pmp_backend.settings import Settings
from pmp_backend.testing import TEST_DATABASE_URL, FakeLLM
from tests.conftest import add_member, create_project, ready_to_work
from tests.test_post_suggestions import listed, run_at
from tests.test_weekly_photos import jpeg, scene
from tests.test_weekly_photos import upload as upload_photo
from tests.test_weekly_updates import WEDNESDAY_17, logged_in_student, set_settings

BRUSSELS = ZoneInfo("Europe/Brussels")


def close_week_of(project_id: int) -> None:
    engine = create_engine(TEST_DATABASE_URL)
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE weekly_updates SET closes_at = closes_at - interval '7 days' "
                "WHERE project_id = :p"
            ),
            {"p": project_id},
        )
    engine.dispose()


class Teams:
    """Projects with one Member each, who upload a photo per week."""

    def __init__(self, client: TestClient) -> None:
        self.client = client
        self.staff = ready_to_work(client, "superuser")
        set_settings(client, self.staff, WEDNESDAY_17)
        self.members: dict[str, dict] = {}
        self.ids: dict[str, int] = {}

    def project(self, title: str) -> int:
        project = create_project(self.client, self.staff, title)
        student, headers = logged_in_student(self.client, self.staff, title + "member")
        add_member(self.client, self.staff, project, student)
        self.members[title], self.ids[title] = headers, project
        return project

    def week(self, title: str, seed: int = 1) -> str:
        """A photo this week; the week's closing moment."""
        upload_photo(self.client, self.members[title], jpeg(scene(seed=seed)))
        mine = self.client.get("/api/my-weekly-update", headers=self.members[title])
        return mine.json()["current"]["closes_at"]


def make_suggestions(
    client, llm, settings, staff: dict, closes_at: str
) -> dict[str, list[int]]:
    """Let the AI make every suggestion that is due; their ids per Project."""
    moment = suggestions.generate_at(datetime.fromisoformat(closes_at))
    run_at(client, llm, settings, moment)
    found: dict[str, list[int]] = {}
    for suggestion in listed(client, staff):
        found.setdefault(suggestion["project"]["title"], []).append(suggestion["id"])
    return found


def act(client: TestClient, headers: dict, suggestion_id: int, action: str):
    return client.post(
        f"/api/post-suggestions/{suggestion_id}/{action}", headers=headers
    )


def scheduled(client: TestClient, headers: dict) -> list[tuple[str, datetime]]:
    body = client.get("/api/scheduled-posts", headers=headers).json()
    return [
        (s["project"]["title"], datetime.fromisoformat(s["scheduled_for"]))
        for s in body["scheduled"]
    ]


def three_projects(client, llm, settings) -> tuple[Teams, dict[str, list[int]]]:
    teams = Teams(client)
    for title in ("Alpha", "Bravo", "Charlie"):
        teams.project(title)
        closes = teams.week(title)
    return teams, make_suggestions(client, llm, settings, teams.staff, closes)


def test_posting_gives_the_next_free_posting_times_in_order(
    client: TestClient, llm: FakeLLM, settings: Settings
):
    teams, found = three_projects(client, llm, settings)
    for title in ("Bravo", "Alpha", "Charlie"):
        response = act(client, teams.staff, found[title][0], "post")
        assert response.status_code == 200, response.text
        assert response.json()["state"] == "scheduled"

    line = scheduled(client, teams.staff)

    assert [title for title, _ in line] == ["Bravo", "Alpha", "Charlie"]
    moments = [moment for _, moment in line]
    assert moments == sorted(set(moments))
    now = datetime.now(BRUSSELS)
    assert moments[0] >= now + timedelta(minutes=10)
    for moment in moments:
        local = moment.astimezone(BRUSSELS)
        assert local.weekday() < 5
        assert local.strftime("%H:%M") in ("12:00", "19:00")
    assert (
        list(posting.posting_times([0, 1, 2, 3, 4], ["12:00", "19:00"], now))[:3]
        == moments
    )


def test_never_the_same_project_twice_in_a_row(
    client: TestClient, llm: FakeLLM, settings: Settings
):
    teams = Teams(client)
    teams.project("Alpha")
    teams.project("Bravo")
    teams.week("Alpha", seed=1)
    close_week_of(teams.ids["Alpha"])
    teams.week("Bravo", seed=2)
    closes = teams.week("Alpha", seed=3)
    found = make_suggestions(client, llm, settings, teams.staff, closes)
    assert len(found["Alpha"]) == 2

    for suggestion_id in (*found["Alpha"], found["Bravo"][0]):
        act(client, teams.staff, suggestion_id, "post")

    assert [title for title, _ in scheduled(client, teams.staff)] == [
        "Alpha",
        "Bravo",
        "Alpha",
    ]


def test_pulling_back_moves_the_others_up(
    client: TestClient, llm: FakeLLM, settings: Settings
):
    teams, found = three_projects(client, llm, settings)
    for title in ("Alpha", "Bravo", "Charlie"):
        act(client, teams.staff, found[title][0], "post")
    before = scheduled(client, teams.staff)

    response = act(client, teams.staff, found["Alpha"][0], "pull-back")

    assert response.status_code == 200, response.text
    assert response.json()["state"] == "waiting"
    after = scheduled(client, teams.staff)
    assert [title for title, _ in after] == ["Bravo", "Charlie"]
    assert [moment for _, moment in after] == [moment for _, moment in before[:2]]


def test_due_posts_are_to_post_by_hand_until_someone_posts_them(
    client: TestClient, llm: FakeLLM, settings: Settings
):
    teams, found = three_projects(client, llm, settings)
    act(client, teams.staff, found["Alpha"][0], "post")
    [(_, moment)] = scheduled(client, teams.staff)
    teacher = ready_to_work(client, "teacher")

    with client.app.state.sessionmaker() as session:
        assert posting.run_once(session, moment - timedelta(minutes=1)) == []
        assert posting.run_once(session, moment) == [found["Alpha"][0]]

    body = client.get("/api/scheduled-posts", headers=teacher).json()
    assert [s["id"] for s in body["to_post"]] == [found["Alpha"][0]]
    assert body["scheduled"] == []

    response = act(client, teacher, found["Alpha"][0], "posted")

    assert response.status_code == 200, response.text
    done = response.json()
    assert (done["state"], done["posted_by"]) == ("posted_by_hand", "Teacher Account")
    with client.app.state.sessionmaker() as session:
        assert session.get(WeeklyMedium, done["chosen"]["id"]).posted is True
    assert client.get("/api/scheduled-posts", headers=teacher).json()["to_post"] == []


def test_archiving_doesnt_cancel_a_scheduled_post(
    client: TestClient, llm: FakeLLM, settings: Settings
):
    teams, found = three_projects(client, llm, settings)
    act(client, teams.staff, found["Alpha"][0], "post")
    teams.client.delete(
        f"/api/projects/{teams.ids['Alpha']}/members/"
        f"{client.get('/api/auth/me', headers=teams.members['Alpha']).json()['id']}",
        headers=teams.staff,
    )

    client.post(f"/api/projects/{teams.ids['Alpha']}/archive", headers=teams.staff)

    assert [title for title, _ in scheduled(client, teams.staff)] == ["Alpha"]


def test_only_waiting_suggestions_can_be_posted(
    client: TestClient, llm: FakeLLM, settings: Settings
):
    teams, found = three_projects(client, llm, settings)
    refused = client.post(
        f"/api/post-suggestions/{found['Alpha'][0]}/refuse",
        json={},
        headers=teams.staff,
    )
    assert refused.status_code == 200, refused.text
    assert act(client, teams.staff, found["Alpha"][0], "post").status_code == 409
    assert act(client, teams.staff, found["Bravo"][0], "pull-back").status_code == 409
    assert act(client, teams.staff, found["Bravo"][0], "posted").status_code == 409
    student = teams.members["Charlie"]
    assert act(client, student, found["Charlie"][0], "post").status_code == 403
