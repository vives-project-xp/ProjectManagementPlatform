from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from tests.conftest import add_member, create_project, ready_to_work

BRUSSELS = ZoneInfo("Europe/Brussels")


def day(days: int) -> date:
    return datetime.now(BRUSSELS).date() + timedelta(days=days)


def at(days: int, hour: int, minute: int = 0) -> str:
    d = day(days)
    return datetime(d.year, d.month, d.day, hour, minute, tzinfo=BRUSSELS).isoformat()


def add_meeting(client, staff, project_id: int, days: int, **extra):
    body = {
        "starts_at": at(days, 10),
        "ends_at": at(days, 11),
        "place": "B2.14",
    } | extra
    return client.post(f"/api/projects/{project_id}/meetings", json=body, headers=staff)


def set_slot(client, staff, project_id: int, weekday: int, place="B2.14"):
    return client.put(
        f"/api/projects/{project_id}/weekly-slot",
        json={"weekday": weekday, "starts": "10:00", "ends": "10:30", "place": place},
        headers=staff,
    )


def planning(client, staff, project_id: int) -> dict:
    return client.get(f"/api/projects/{project_id}/planning", headers=staff).json()


def kinds(body: dict) -> list[tuple[str, str]]:
    return [(item["kind"], item["when"]) for item in body["items"]]


def test_a_meeting_is_added_changed_and_deleted(client: TestClient):
    staff = ready_to_work(client, "teacher")
    drone = create_project(client, staff, "Drone")

    added = add_meeting(
        client, staff, drone, 2, place="https://teams.example/x", note="Bring the demo"
    )
    meeting = added.json()["id"]
    shown = planning(client, staff, drone)
    edited = client.put(
        f"/api/meetings/{meeting}",
        json={"starts_at": at(3, 14), "ends_at": at(3, 15), "place": "B2.15"},
        headers=staff,
    )
    deleted = client.delete(f"/api/meetings/{meeting}", headers=staff)

    assert added.status_code == 201, added.text
    assert shown["items"] == [
        {
            "kind": "meeting",
            "id": meeting,
            "project_id": drone,
            "project_title": "Drone",
            "title": "Meeting",
            "starts_at": shown["items"][0]["starts_at"],
            "ends_at": shown["items"][0]["ends_at"],
            "place": "https://teams.example/x",
            "details": "Bring the demo",
            "when": "upcoming",
        }
    ]
    assert datetime.fromisoformat(shown["items"][0]["starts_at"]) == (
        datetime.fromisoformat(at(2, 10))
    )
    assert edited.json()["place"] == "B2.15"
    assert deleted.status_code == 204
    assert planning(client, staff, drone)["items"] == []


def test_a_meeting_must_end_after_it_starts(client: TestClient):
    staff = ready_to_work(client, "teacher")
    drone = create_project(client, staff, "Drone")

    response = add_meeting(client, staff, drone, 2, ends_at=at(2, 9))

    assert response.status_code == 422
    assert response.json()["detail"] == "A meeting must end after it starts."


def test_the_weekly_slot_shows_this_weeks_meeting(client: TestClient):
    staff = ready_to_work(client, "teacher")
    drone = create_project(client, staff, "Drone")
    weekday = day(2).weekday()

    response = set_slot(client, staff, drone, weekday)
    shown = planning(client, staff, drone)

    assert response.status_code == 200, response.text
    assert response.json() | {"skipped": []} == {
        "project_id": drone,
        "project_title": "Drone",
        "weekday": weekday,
        "weekday_name": day(2).strftime("%A"),
        "starts": "10:00:00",
        "ends": "10:30:00",
        "place": "B2.14",
        "skipped": [],
    }
    assert kinds(shown) == [("weekly", "upcoming")]
    occurrence = shown["items"][0]
    assert occurrence["title"] == "Weekly meeting"
    assert datetime.fromisoformat(occurrence["starts_at"]) == (
        datetime.fromisoformat(at(2, 10))
    )
    assert shown["weekly_slot"]["place"] == "B2.14"


def test_the_weekly_slot_can_be_changed_and_cleared(client: TestClient):
    staff = ready_to_work(client, "teacher")
    drone = create_project(client, staff, "Drone")
    set_slot(client, staff, drone, 1)

    changed = set_slot(client, staff, drone, 3, place="Online")
    cleared = client.delete(f"/api/projects/{drone}/weekly-slot", headers=staff)

    assert changed.json()["weekday_name"] == "Thursday"
    assert cleared.status_code == 204
    assert planning(client, staff, drone) == {"items": [], "weekly_slot": None}


def test_a_slot_must_end_after_it_starts(client: TestClient):
    staff = ready_to_work(client, "teacher")
    drone = create_project(client, staff, "Drone")

    response = client.put(
        f"/api/projects/{drone}/weekly-slot",
        json={"weekday": 1, "starts": "10:00", "ends": "09:00", "place": "B2.14"},
        headers=staff,
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "The weekly meeting must end after it starts."


def test_a_skipped_date_has_no_weekly_meeting(client: TestClient):
    staff = ready_to_work(client, "teacher")
    drone = create_project(client, staff, "Drone")
    set_slot(client, staff, drone, day(1).weekday())

    skipped = client.post(
        f"/api/projects/{drone}/weekly-slot/skips/{day(1)}", headers=staff
    )
    without = planning(client, staff, drone)
    unskipped = client.delete(
        f"/api/projects/{drone}/weekly-slot/skips/{day(1)}", headers=staff
    )

    assert skipped.status_code == 200, skipped.text
    assert skipped.json()["skipped"] == [day(1).isoformat()]
    assert without["items"] == []
    assert unskipped.json()["skipped"] == []
    assert kinds(planning(client, staff, drone)) == [("weekly", "upcoming")]


def test_only_the_slots_weekday_can_be_skipped(client: TestClient):
    staff = ready_to_work(client, "teacher")
    drone = create_project(client, staff, "Drone")
    set_slot(client, staff, drone, day(1).weekday())

    response = client.post(
        f"/api/projects/{drone}/weekly-slot/skips/{day(2)}", headers=staff
    )

    assert response.status_code == 422
    assert response.json()["detail"] == (
        f"{day(2):%d/%m/%Y} isn't a {day(1):%A}, the day of the weekly meeting."
    )


def test_skipping_without_a_slot_is_refused(client: TestClient):
    staff = ready_to_work(client, "teacher")
    drone = create_project(client, staff, "Drone")

    response = client.post(
        f"/api/projects/{drone}/weekly-slot/skips/{day(1)}", headers=staff
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Drone has no weekly meeting."


def test_archived_projects_keep_meetings_read_only(client: TestClient):
    staff = ready_to_work(client, "teacher")
    drone = create_project(client, staff, "Drone")
    meeting = add_meeting(client, staff, drone, 2).json()["id"]
    set_slot(client, staff, drone, day(1).weekday())
    client.post(f"/api/projects/{drone}/archive", headers=staff)

    added = add_meeting(client, staff, drone, 3)
    deleted = client.delete(f"/api/meetings/{meeting}", headers=staff)
    slot = set_slot(client, staff, drone, 2)
    shown = planning(client, staff, drone)

    assert added.status_code == 409
    assert deleted.status_code == 409
    assert slot.status_code == 409
    # The meeting stays; an Archived Project has no weekly meetings any more.
    assert kinds(shown) == [("meeting", "upcoming")]
    assert shown["weekly_slot"]["weekday"] == day(1).weekday()


def test_the_overview_shows_meetings_and_every_weekly_slot(client: TestClient):
    staff = ready_to_work(client, "superuser")
    drone = create_project(client, staff, "Drone")
    robot = create_project(client, staff, "Robot")
    add_meeting(client, staff, drone, 1)
    add_meeting(client, staff, drone, -1)
    set_slot(client, staff, robot, day(0).weekday())
    teacher = ready_to_work(client, "teacher")

    response = client.get("/api/planning", headers=teacher)

    body = response.json()
    assert [(i["kind"], i["project_title"], i["when"]) for i in body["items"]] == [
        ("weekly", "Robot", "today"),
        ("meeting", "Drone", "upcoming"),
    ]
    assert [s["project_title"] for s in body["weekly_slots"]] == ["Robot"]


def test_a_student_sees_meetings_and_the_weekly_slot(client: TestClient):
    staff = ready_to_work(client, "superuser")
    drone = create_project(client, staff, "Drone")
    students = client.get("/api/users?role=student", headers=staff).json()
    add_member(client, staff, drone, students[0]["id"])
    add_meeting(client, staff, drone, 2)
    set_slot(client, staff, drone, day(4).weekday())
    student = ready_to_work(client, "student")

    response = client.get("/api/my-project/planning", headers=student)

    assert kinds(response.json()) == [("meeting", "upcoming"), ("weekly", "upcoming")]
    assert response.json()["weekly_slot"]["place"] == "B2.14"


def test_students_cannot_plan_meetings(client: TestClient):
    staff = ready_to_work(client, "teacher")
    drone = create_project(client, staff, "Drone")
    student = ready_to_work(client, "student")

    assert add_meeting(client, student, drone, 1).status_code == 403
    assert set_slot(client, student, drone, 1).status_code == 403
    response = client.get(f"/api/projects/{drone}/planning", headers=student)
    assert response.status_code == 403
