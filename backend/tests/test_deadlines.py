from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from tests.conftest import add_member, create_project, ready_to_work

BRUSSELS = ZoneInfo("Europe/Brussels")


def at(days: int, hour: int = 23, minute: int = 59) -> str:
    """A moment `days` from today, in Belgian time."""
    day = datetime.now(BRUSSELS).date() + timedelta(days=days)
    return datetime(
        day.year, day.month, day.day, hour, minute, tzinfo=BRUSSELS
    ).isoformat()


def add(
    client: TestClient, staff, project_id: int | None, title: str, due_at: str, **extra
):
    path = f"/api/projects/{project_id}/deadlines" if project_id else "/api/deadlines"
    return client.post(
        path, json={"title": title, "due_at": due_at, **extra}, headers=staff
    )


def titles(response) -> list[tuple[str, str]]:
    return [(d["title"], d["when"]) for d in response.json()]


def test_a_project_shows_its_own_and_the_all_projects_deadlines(client: TestClient):
    staff = ready_to_work(client, "teacher")
    drone = create_project(client, staff, "Drone")
    robot = create_project(client, staff, "Robot")

    created = add(
        client, staff, drone, "Prototype demo", at(3, 14, 0), description="In B2.14"
    )
    add(client, staff, None, "Final presentation", at(10))
    add(client, staff, robot, "Robot only", at(1))
    add(client, staff, drone, "Kick-off", at(-2))
    add(client, staff, drone, "Poster", at(0))

    assert created.status_code == 201, created.text
    assert created.json() | {"id": 0} == {
        "id": 0,
        "project_id": drone,
        "project_title": "Drone",
        "title": "Prototype demo",
        "due_at": created.json()["due_at"],
        "description": "In B2.14",
        "when": "upcoming",
    }
    assert datetime.fromisoformat(created.json()["due_at"]) == datetime.fromisoformat(
        at(3, 14, 0)
    )
    shown = client.get(f"/api/projects/{drone}/deadlines", headers=staff)
    assert titles(shown) == [
        ("Kick-off", "earlier"),
        ("Poster", "today"),
        ("Prototype demo", "upcoming"),
        ("Final presentation", "upcoming"),
    ]
    assert shown.json()[3]["project_id"] is None


def test_a_deadline_can_be_edited_and_deleted(client: TestClient):
    staff = ready_to_work(client, "teacher")
    drone = create_project(client, staff, "Drone")
    deadline = add(client, staff, drone, "Demo", at(3)).json()["id"]

    edited = client.put(
        f"/api/deadlines/{deadline}",
        json={"title": "Demo moved", "due_at": at(5)},
        headers=staff,
    )
    deleted = client.delete(f"/api/deadlines/{deadline}", headers=staff)

    assert edited.status_code == 200, edited.text
    assert edited.json()["title"] == "Demo moved"
    assert deleted.status_code == 204
    assert client.get(f"/api/projects/{drone}/deadlines", headers=staff).json() == []


def test_an_empty_title_or_a_time_without_zone_is_refused(client: TestClient):
    staff = ready_to_work(client, "teacher")
    drone = create_project(client, staff, "Drone")

    empty = add(client, staff, drone, "  ", at(1))
    naive = add(client, staff, drone, "Demo", "2026-11-12T23:59:00")

    assert empty.status_code == 422
    assert naive.status_code == 422


def test_archived_projects_keep_their_deadlines_read_only(client: TestClient):
    staff = ready_to_work(client, "teacher")
    drone = create_project(client, staff, "Drone")
    deadline = add(client, staff, drone, "Demo", at(3)).json()["id"]
    add(client, staff, None, "Final presentation", at(10))
    client.post(f"/api/projects/{drone}/archive", headers=staff)

    added = add(client, staff, drone, "Another", at(4))
    edited = client.put(
        f"/api/deadlines/{deadline}",
        json={"title": "X", "due_at": at(5)},
        headers=staff,
    )
    deleted = client.delete(f"/api/deadlines/{deadline}", headers=staff)
    shown = client.get(f"/api/projects/{drone}/deadlines", headers=staff)

    assert added.status_code == 409
    assert added.json()["detail"] == (
        "Drone is archived, so it cannot be changed. Restore it first."
    )
    assert edited.status_code == 409
    assert deleted.status_code == 409
    # Deadlines for every Project only count for Active Projects.
    assert titles(shown) == [("Demo", "upcoming")]


def test_planning_shows_what_is_coming_across_active_projects(client: TestClient):
    staff = ready_to_work(client, "superuser")
    teachers = client.get("/api/users?role=teacher", headers=staff).json()
    mine = create_project(client, staff, "Drone")
    other_owner = client.post(
        "/api/users",
        json={
            "role": "teacher",
            "first_name": "Other",
            "last_name": "Teacher",
            "email": "other@vives.be",
        },
        headers=staff,
    ).json()["id"]
    theirs = client.post(
        "/api/projects",
        json={
            "title": "Robot",
            "product_owner_id": other_owner,
            "team_size_min": 1,
            "team_size_max": 3,
        },
        headers=staff,
    ).json()["id"]
    old = create_project(client, staff, "Old one")
    add(client, staff, mine, "Drone demo", at(2))
    add(client, staff, theirs, "Robot demo", at(1))
    add(client, staff, None, "Final presentation", at(0, 9, 0))
    add(client, staff, mine, "Past", at(-1))
    add(client, staff, old, "Archived one", at(3))
    client.post(f"/api/projects/{old}/archive", headers=staff)
    teacher = ready_to_work(client, "teacher")

    everything = client.get("/api/planning", headers=teacher)
    only_mine = client.get("/api/planning?mine=true", headers=teacher)

    assert teachers[0]["email"] == "teacher@pmp.local"
    assert titles(everything) == [
        ("Final presentation", "today"),
        ("Robot demo", "upcoming"),
        ("Drone demo", "upcoming"),
    ]
    assert [d["project_title"] for d in everything.json()] == [None, "Robot", "Drone"]
    assert titles(only_mine) == [
        ("Final presentation", "today"),
        ("Drone demo", "upcoming"),
    ]


def test_a_student_sees_their_projects_deadlines(client: TestClient):
    staff = ready_to_work(client, "superuser")
    drone = create_project(client, staff, "Drone")
    students = client.get("/api/users?role=student", headers=staff).json()
    add_member(client, staff, drone, students[0]["id"])
    add(client, staff, drone, "Demo", at(2))
    add(client, staff, None, "Final presentation", at(9))
    student = ready_to_work(client, "student")

    response = client.get("/api/my-project/planning", headers=student)

    assert titles(response) == [
        ("Demo", "upcoming"),
        ("Final presentation", "upcoming"),
    ]


def test_a_student_without_project_sees_nothing(client: TestClient):
    student = ready_to_work(client, "student")

    assert client.get("/api/my-project/planning", headers=student).json() == []


def test_students_cannot_plan(client: TestClient):
    staff = ready_to_work(client, "teacher")
    drone = create_project(client, staff, "Drone")
    deadline = add(client, staff, drone, "Demo", at(3)).json()["id"]
    student = ready_to_work(client, "student")

    assert add(client, student, drone, "Mine", at(1)).status_code == 403
    assert add(client, student, None, "Mine", at(1)).status_code == 403
    assert (
        client.delete(f"/api/deadlines/{deadline}", headers=student).status_code == 403
    )
    assert client.get("/api/planning", headers=student).status_code == 403
    response = client.get(f"/api/projects/{drone}/deadlines", headers=student)
    assert response.status_code == 403
