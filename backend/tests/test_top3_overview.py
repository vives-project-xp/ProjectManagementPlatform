from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, update

from pmp_backend.models import Top3Round
from tests.conftest import (
    NEW_STUDENT,
    add_member,
    auth,
    create_project,
    create_student,
    ready_to_work,
)


def in_hours(hours: float) -> str:
    return (datetime.now(UTC) + timedelta(hours=hours)).isoformat()


OWN_PASSWORD = "lisa-own-password"


def log_in_new_student(
    client: TestClient, staff: dict[str, str], student_id: int, email: str
) -> dict[str, str]:
    """Headers of a Student made with create_student, past the password change;
    their generated Temporary password comes from a reset."""
    password = client.post(
        f"/api/users/{student_id}/reset-password", headers=staff
    ).json()["temporary_password"]
    token = client.post(
        "/api/auth/login", json={"email": email, "password": password}
    ).json()["access_token"]
    client.post(
        "/api/auth/change-password",
        json={"current_password": password, "new_password": OWN_PASSWORD},
        headers=auth(token),
    )
    return auth(token)


def submit(client: TestClient, headers, project_ids: list[int]) -> None:
    response = client.post(
        "/api/my-top3", json={"project_ids": project_ids}, headers=headers
    )
    assert response.status_code == 200, response.text


def overview(client: TestClient, headers, query: str = "") -> dict:
    response = client.get(f"/api/top3/overview{query}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def row(body: dict, name: str) -> dict:
    return next(student for student in body["students"] if student["name"] == name)


def ranked_titles(student: dict) -> list:
    return [(c["rank"], c["title"], c["available"]) for c in student["top3"]]


@pytest.fixture
def setup(client: TestClient):
    """Three open Projects, an open round, Lisa (year 2) with a Top 3 and the
    starting Student (year 1) without one."""
    staff = ready_to_work(client, "superuser")
    ids = []
    for title in ("Drone", "Robot", "Smart Greenhouse"):
        project = create_project(client, staff, title)
        client.put(
            f"/api/projects/{project}/open-for-choice",
            json={"open": True},
            headers=staff,
        )
        ids.append(project)
    client.put("/api/top3/round", json={"deadline": in_hours(24)}, headers=staff)
    lisa = create_student(client, staff, "Lisa")
    lisa_headers = log_in_new_student(client, staff, lisa, "lisa@student.vives.be")
    submit(client, lisa_headers, [ids[1], ids[0], ids[2]])
    return staff, ids, lisa


def test_overview_shows_every_active_student_and_their_top3(client: TestClient, setup):
    staff, ids, _ = setup

    body = overview(client, staff)

    assert [s["name"] for s in body["students"]] == ["Student Account", "Lisa Peeters"]
    lisa = row(body, "Lisa Peeters")
    assert ranked_titles(lisa) == [
        (1, "Robot", True),
        (2, "Drone", True),
        (3, "Smart Greenhouse", True),
    ]
    assert lisa["top3"][0]["project_id"] == ids[1]
    assert lisa["submitted_at"] is not None
    assert lisa["programme"] == "Electronics-ICT"
    assert lisa["year"] == "2"
    assert lisa["project"] is None
    assert row(body, "Student Account")["top3"] is None


def test_overview_summarises_each_open_project(client: TestClient, setup):
    staff, ids, _ = setup
    submit(client, ready_to_work(client, "student"), [ids[1], ids[2], ids[0]])

    summary = overview(client, staff)["summary"]

    assert [(s["title"], s["first"], s["second"], s["third"]) for s in summary] == [
        ("Drone", 0, 1, 1),
        ("Robot", 2, 0, 0),
        ("Smart Greenhouse", 0, 1, 1),
    ]


def test_overview_filters(client: TestClient, setup):
    staff, _, _ = setup
    client.post("/api/programmes", json={"name": "Chemistry"}, headers=staff)
    client.post(
        "/api/users",
        json=NEW_STUDENT
        | {
            "first_name": "Bram",
            "email": "bram@student.vives.be",
            "programme": "Chemistry",
        },
        headers=staff,
    )

    def names(query: str) -> list[str]:
        return [s["name"] for s in overview(client, staff, query)["students"]]

    assert names("?programme=chemistry") == ["Bram Peeters"]
    assert names("?year=1") == ["Student Account"]
    assert names("?without_top3=true") == ["Student Account", "Bram Peeters"]


def test_unavailable_choices_are_marked(client: TestClient, setup):
    staff, ids, _ = setup
    client.put(
        f"/api/projects/{ids[0]}/open-for-choice", json={"open": False}, headers=staff
    )
    client.delete(f"/api/projects/{ids[2]}", headers=staff)

    lisa = row(overview(client, staff), "Lisa Peeters")

    assert ranked_titles(lisa) == [
        (1, "Robot", True),
        (2, "Drone", False),
        (3, None, False),
    ]


def test_overview_shows_the_current_project(client: TestClient, setup):
    staff, ids, lisa = setup
    add_member(client, staff, ids[1], lisa)

    project = row(overview(client, staff), "Lisa Peeters")["project"]

    assert project == {"id": ids[1], "title": "Robot"}


def test_deactivated_students_are_left_out(client: TestClient, setup):
    staff, _, lisa = setup
    client.post(f"/api/users/{lisa}/deactivate", headers=staff)

    names = [s["name"] for s in overview(client, staff)["students"]]

    assert names == ["Student Account"]


# Reset


def test_reset_lets_the_student_choose_again(client: TestClient, setup):
    staff, ids, lisa = setup

    response = client.delete(f"/api/top3/students/{lisa}", headers=staff)

    assert response.status_code == 204, response.text
    assert row(overview(client, staff), "Lisa Peeters")["top3"] is None
    token = client.post(
        "/api/auth/login",
        json={"email": "lisa@student.vives.be", "password": OWN_PASSWORD},
    ).json()["access_token"]
    submit(client, auth(token), ids)


def test_reset_needs_an_open_round(client: TestClient, setup):
    staff, _, lisa = setup
    with client.app.state.sessionmaker() as session:
        session.execute(
            update(Top3Round).values(deadline=func.now() - timedelta(minutes=1))
        )
        session.commit()

    response = client.delete(f"/api/top3/students/{lisa}", headers=staff)

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "The Top 3 round is closed, so a Top 3 can't be reset."
    )


def test_reset_without_a_top3_is_not_found(client: TestClient, setup):
    staff, _, _ = setup
    student = row(overview(client, staff), "Student Account")["id"]

    without = client.delete(f"/api/top3/students/{student}", headers=staff)
    unknown = client.delete("/api/top3/students/9999", headers=staff)

    assert without.status_code == 404
    assert without.json()["detail"] == "Student Account has no Top 3."
    assert unknown.status_code == 404


# Deleting


def test_deleting_a_student_removes_their_top3(client: TestClient, setup):
    staff, _, lisa = setup

    response = client.delete(f"/api/users/{lisa}", headers=staff)

    assert response.status_code == 204, response.text
    summary = overview(client, staff)["summary"]
    assert all(s["first"] + s["second"] + s["third"] == 0 for s in summary)


# Access


def test_students_cannot_see_the_overview_or_reset(client: TestClient, setup):
    _, _, lisa = setup
    student = ready_to_work(client, "student")

    assert client.get("/api/top3/overview", headers=student).status_code == 403
    assert (
        client.delete(f"/api/top3/students/{lisa}", headers=student).status_code == 403
    )
