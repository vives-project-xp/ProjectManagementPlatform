from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from pmp_backend.testing import TEST_DATABASE_URL
from tests.conftest import (
    add_member,
    auth,
    create_project,
    create_student,
    ready_to_work,
)

BRUSSELS = ZoneInfo("Europe/Brussels")
DEFAULTS = {
    "upload_weekday": None,
    "upload_time": None,
    "instagram_weekdays": [0, 1, 2, 3, 4],
    "instagram_times": ["12:00", "19:00"],
    "fixed_hashtags": "#VIVEShogeschool #ElektronicaICT",
}
WEDNESDAY_17 = DEFAULTS | {"upload_weekday": 2, "upload_time": "17:00"}


def set_settings(client: TestClient, staff: dict, body: dict):
    return client.put("/api/social/settings", json=body, headers=staff)


def logged_in_student(
    client: TestClient, staff: dict, first_name: str
) -> tuple[int, dict]:
    """A new Student's id and auth headers, past the password change."""
    user_id = create_student(client, staff, first_name)
    password = client.post(f"/api/users/{user_id}/reset-password", headers=staff)
    temporary = password.json()["temporary_password"]
    email = f"{first_name.lower()}@student.vives.be"
    token = client.post(
        "/api/auth/login", json={"email": email, "password": temporary}
    ).json()["access_token"]
    response = client.post(
        "/api/auth/change-password",
        json={"current_password": temporary, "new_password": "own-password-1"},
        headers=auth(token),
    )
    assert response.status_code == 204, response.text
    return user_id, auth(token)


def drone_team(client: TestClient) -> tuple[dict, int, dict, dict]:
    """Superuser headers, Project Drone with Members Lisa and Tom (logged in)."""
    staff = ready_to_work(client, "superuser")
    project = create_project(client, staff, "Drone")
    team = []
    for name in ("Lisa", "Tom"):
        user_id, headers = logged_in_student(client, staff, name)
        add_member(client, staff, project, user_id)
        team.append(headers)
    return staff, project, team[0], team[1]


def close_the_open_week(project_id: int) -> None:
    """Move the Project's open Upload week into the past, as if it had closed."""
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


# Settings


def test_the_superuser_sees_the_defaults_and_changes_them(client: TestClient):
    staff = ready_to_work(client, "superuser")
    assert client.get("/api/social/settings", headers=staff).json() == DEFAULTS

    changed = WEDNESDAY_17 | {
        "instagram_weekdays": [4, 0, 0],
        "instagram_times": ["19:30"],
        "fixed_hashtags": "  #VIVES   #EOICT ",
    }
    response = set_settings(client, staff, changed)

    assert response.status_code == 200, response.text
    expected = WEDNESDAY_17 | {
        "instagram_weekdays": [0, 4],
        "instagram_times": ["19:30"],
        "fixed_hashtags": "#VIVES #EOICT",
    }
    assert response.json() == expected
    assert client.get("/api/social/settings", headers=staff).json() == expected


def test_only_the_superuser_manages_the_settings(client: TestClient):
    teacher = ready_to_work(client, "teacher")
    assert client.get("/api/social/settings", headers=teacher).status_code == 403
    assert set_settings(client, teacher, WEDNESDAY_17).status_code == 403


def test_settings_that_make_no_sense_are_refused(client: TestClient):
    staff = ready_to_work(client, "superuser")
    for wrong in (
        DEFAULTS | {"upload_weekday": 2},
        DEFAULTS | {"instagram_weekdays": []},
        DEFAULTS | {"instagram_times": []},
        DEFAULTS | {"instagram_times": ["09:00", "12:00", "19:00"]},
        DEFAULTS | {"fixed_hashtags": "VIVES"},
        DEFAULTS | {"fixed_hashtags": ""},
    ):
        response = set_settings(client, staff, wrong)
        assert response.status_code == 422, wrong
        assert response.json()["detail"]
    for invalid in (
        WEDNESDAY_17 | {"upload_weekday": 7},
        WEDNESDAY_17 | {"upload_time": "25:00"},
    ):
        assert set_settings(client, staff, invalid).status_code == 422


# Weekly updates


def test_members_write_one_weekly_update_together(client: TestClient):
    staff, project, lisa, tom = drone_team(client)
    set_settings(client, staff, WEDNESDAY_17)

    response = client.put(
        "/api/my-weekly-update", json={"text": "  Built the frame. "}, headers=lisa
    )
    assert response.status_code == 200, response.text
    client.put(
        "/api/my-weekly-update",
        json={"text": "Built the frame and tested the motors."},
        headers=tom,
    )

    seen = client.get("/api/my-weekly-update", headers=lisa).json()
    assert seen["project"] == {"id": project, "title": "Drone"}
    current = seen["current"]
    assert current["text"] == "Built the frame and tested the motors."
    assert current["edited_by"] == "Tom Peeters"
    assert current["is_open"] is True
    closes = datetime.fromisoformat(current["closes_at"]).astimezone(BRUSSELS)
    assert (closes.weekday(), closes.hour, closes.minute) == (2, 17, 0)
    now = datetime.now(BRUSSELS)
    assert now < closes <= now + timedelta(days=7)
    assert seen["earlier"] == []


def test_nothing_to_write_before_the_upload_deadline_is_set(client: TestClient):
    _, _, lisa, _ = drone_team(client)

    assert client.get("/api/my-weekly-update", headers=lisa).json()["current"] is None
    response = client.put("/api/my-weekly-update", json={"text": "Hi"}, headers=lisa)
    assert response.status_code == 422
    assert response.json()["detail"] == "The Upload deadline hasn't been set yet."


def test_a_closed_week_is_locked_and_a_new_one_starts(client: TestClient):
    staff, project, lisa, _ = drone_team(client)
    set_settings(client, staff, WEDNESDAY_17)
    client.put("/api/my-weekly-update", json={"text": "Week one."}, headers=lisa)

    close_the_open_week(project)
    seen = client.get("/api/my-weekly-update", headers=lisa).json()
    assert seen["current"]["text"] == ""
    assert seen["current"]["edited_by"] is None
    assert [week["text"] for week in seen["earlier"]] == ["Week one."]
    assert seen["earlier"][0]["is_open"] is False

    client.put("/api/my-weekly-update", json={"text": "Week two."}, headers=lisa)
    seen = client.get("/api/my-weekly-update", headers=lisa).json()
    assert seen["current"]["text"] == "Week two."
    assert [week["text"] for week in seen["earlier"]] == ["Week one."]


def test_a_new_upload_deadline_moves_the_open_week(client: TestClient):
    staff, _, lisa, _ = drone_team(client)
    set_settings(client, staff, WEDNESDAY_17)
    client.put("/api/my-weekly-update", json={"text": "Draft."}, headers=lisa)

    set_settings(
        client, staff, WEDNESDAY_17 | {"upload_weekday": 4, "upload_time": "12:30"}
    )

    current = client.get("/api/my-weekly-update", headers=lisa).json()["current"]
    assert current["text"] == "Draft."
    closes = datetime.fromisoformat(current["closes_at"]).astimezone(BRUSSELS)
    assert (closes.weekday(), closes.hour, closes.minute) == (4, 12, 30)


def test_a_too_long_weekly_update_is_refused(client: TestClient):
    staff, _, lisa, _ = drone_team(client)
    set_settings(client, staff, WEDNESDAY_17)
    response = client.put(
        "/api/my-weekly-update", json={"text": "x" * 4001}, headers=lisa
    )
    assert response.status_code == 422


def test_a_student_without_a_project_has_no_weekly_update(client: TestClient):
    staff = ready_to_work(client, "superuser")
    set_settings(client, staff, WEDNESDAY_17)
    student = ready_to_work(client, "student")

    assert client.get("/api/my-weekly-update", headers=student).json() is None
    response = client.put("/api/my-weekly-update", json={"text": "Hi"}, headers=student)
    assert response.status_code == 422
    assert client.get("/api/auth/me", headers=student).json()["project_id"] is None


def test_staff_read_every_weekly_update_of_a_project(client: TestClient):
    staff, project, lisa, _ = drone_team(client)
    set_settings(client, staff, WEDNESDAY_17)
    client.put("/api/my-weekly-update", json={"text": "Week one."}, headers=lisa)
    close_the_open_week(project)
    client.put("/api/my-weekly-update", json={"text": "Week two."}, headers=lisa)

    teacher = ready_to_work(client, "teacher")
    weeks = client.get(f"/api/projects/{project}/weekly-updates", headers=teacher)

    assert weeks.status_code == 200
    assert [(w["text"], w["is_open"]) for w in weeks.json()] == [
        ("Week two.", True),
        ("Week one.", False),
    ]
    assert (
        client.get(f"/api/projects/{project}/weekly-updates", headers=lisa).status_code
        == 403
    )
    assert (
        client.get("/api/projects/999/weekly-updates", headers=teacher).status_code
        == 404
    )


def test_a_deleted_editor_shows_as_deleted_user(client: TestClient):
    staff, project, lisa, _ = drone_team(client)
    set_settings(client, staff, WEDNESDAY_17)
    client.put("/api/my-weekly-update", json={"text": "Week one."}, headers=lisa)
    lisa_id = client.get("/api/auth/me", headers=lisa).json()["id"]
    client.delete(f"/api/projects/{project}/members/{lisa_id}", headers=staff)

    response = client.delete(f"/api/users/{lisa_id}", headers=staff)

    assert response.status_code == 204, response.text
    weeks = client.get(f"/api/projects/{project}/weekly-updates", headers=staff).json()
    assert weeks[0]["edited_by"] == "Deleted user"


def test_deleting_a_project_deletes_its_weekly_updates(client: TestClient):
    staff = ready_to_work(client, "superuser")
    set_settings(client, staff, WEDNESDAY_17)
    project = create_project(client, staff, "Drone")
    student, lisa = logged_in_student(client, staff, "Lisa")
    add_member(client, staff, project, student)
    client.put("/api/my-weekly-update", json={"text": "Hi"}, headers=lisa)
    client.delete(f"/api/projects/{project}/members/{student}", headers=staff)

    assert client.delete(f"/api/projects/{project}", headers=staff).status_code == 204
    assert (
        client.get(f"/api/projects/{project}/weekly-updates", headers=staff).status_code
        == 404
    )


def test_login_shows_whether_a_student_has_a_project(client: TestClient):
    _, project, lisa, _ = drone_team(client)
    assert client.get("/api/auth/me", headers=lisa).json()["project_id"] == project
