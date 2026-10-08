from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update

from pmp_backend.models import Top3Choice, Top3Round
from tests.conftest import create_project, create_student, ready_to_work


def in_hours(hours: float) -> str:
    return (datetime.now(UTC) + timedelta(hours=hours)).isoformat()


def same_moment(left: str, right: str) -> bool:
    return datetime.fromisoformat(left) == datetime.fromisoformat(right)


def open_for_choice(client: TestClient, headers, project_id: int, value: bool):
    return client.put(
        f"/api/projects/{project_id}/open-for-choice",
        json={"open": value},
        headers=headers,
    )


# Open for choice


@pytest.mark.parametrize("role", ["teacher", "superuser"])
def test_staff_open_and_close_a_project_for_choice(client: TestClient, role: str):
    headers = ready_to_work(client, role)
    project = create_project(client, headers, "Smart Greenhouse")

    opened = open_for_choice(client, headers, project, True)
    listed = client.get("/api/projects", headers=headers).json()
    closed = open_for_choice(client, headers, project, False)

    assert opened.status_code == 200, opened.text
    assert opened.json()["open_for_choice"] is True
    assert listed[0]["open_for_choice"] is True
    assert closed.json()["open_for_choice"] is False


def test_a_new_project_is_not_open_for_choice(client: TestClient):
    headers = ready_to_work(client, "teacher")
    project = create_project(client, headers, "Smart Greenhouse")

    details = client.get(f"/api/projects/{project}", headers=headers).json()

    assert details["open_for_choice"] is False


def test_archiving_closes_a_project_for_choice(client: TestClient):
    headers = ready_to_work(client, "teacher")
    project = create_project(client, headers, "Smart Greenhouse")
    open_for_choice(client, headers, project, True)

    client.post(f"/api/projects/{project}/archive", headers=headers)
    refused = open_for_choice(client, headers, project, True)
    client.post(f"/api/projects/{project}/restore", headers=headers)

    assert refused.status_code == 409
    details = client.get(f"/api/projects/{project}", headers=headers).json()
    assert details["open_for_choice"] is False


# The round


def test_there_is_no_round_at_first(client: TestClient):
    headers = ready_to_work(client, "teacher")

    response = client.get("/api/top3/round", headers=headers)

    assert response.status_code == 200
    assert response.json() == {"deadline": None, "is_open": False}


def test_teacher_opens_the_round_with_a_deadline(client: TestClient):
    headers = ready_to_work(client, "teacher")
    deadline = in_hours(48)

    response = client.put(
        "/api/top3/round", json={"deadline": deadline}, headers=headers
    )

    assert response.status_code == 200, response.text
    assert response.json()["is_open"] is True
    assert same_moment(response.json()["deadline"], deadline)
    shown = client.get("/api/top3/round", headers=headers).json()
    assert same_moment(shown["deadline"], deadline)


def test_the_deadline_can_be_moved(client: TestClient):
    headers = ready_to_work(client, "superuser")
    client.put("/api/top3/round", json={"deadline": in_hours(2)}, headers=headers)
    later = in_hours(72)

    response = client.put("/api/top3/round", json={"deadline": later}, headers=headers)

    assert response.status_code == 200
    assert same_moment(response.json()["deadline"], later)


@pytest.mark.parametrize("path", ["/api/top3/round", "/api/top3/round/new"])
def test_a_deadline_in_the_past_is_refused(client: TestClient, path: str):
    headers = ready_to_work(client, "teacher")
    method = client.put if path.endswith("round") else client.post

    response = method(path, json={"deadline": in_hours(-1)}, headers=headers)

    assert response.status_code == 422
    assert response.json()["detail"] == "The deadline must be in the future."


def test_a_deadline_without_time_zone_is_refused(client: TestClient):
    headers = ready_to_work(client, "teacher")

    response = client.put(
        "/api/top3/round", json={"deadline": "2099-01-01T12:00:00"}, headers=headers
    )

    assert response.status_code == 422


def test_teacher_closes_the_round_early(client: TestClient):
    headers = ready_to_work(client, "teacher")
    client.put("/api/top3/round", json={"deadline": in_hours(48)}, headers=headers)

    response = client.post("/api/top3/round/close", headers=headers)
    again = client.post("/api/top3/round/close", headers=headers)

    assert response.status_code == 200, response.text
    assert response.json()["is_open"] is False
    assert again.status_code == 409
    assert again.json()["detail"] == "The Top 3 round is not open."


def test_a_passed_deadline_closes_the_round(client: TestClient):
    headers = ready_to_work(client, "teacher")
    client.put("/api/top3/round", json={"deadline": in_hours(1)}, headers=headers)
    with client.app.state.sessionmaker() as session:
        session.execute(
            update(Top3Round).values(deadline=func.now() - timedelta(minutes=1))
        )
        session.commit()

    assert client.get("/api/top3/round", headers=headers).json()["is_open"] is False


def choice_count(client: TestClient) -> int:
    with client.app.state.sessionmaker() as session:
        return session.scalar(select(func.count()).select_from(Top3Choice))


def give_a_top3(client: TestClient, headers) -> None:
    """A submitted Top 3, written directly: submitting comes with #39."""
    project = create_project(client, headers, "Smart Greenhouse")
    student = create_student(client, headers, "Lisa")
    with client.app.state.sessionmaker() as session:
        session.add(Top3Choice(student_id=student, rank=1, project_id=project))
        session.commit()


def test_reopening_keeps_the_top3s(client: TestClient):
    headers = ready_to_work(client, "superuser")
    client.put("/api/top3/round", json={"deadline": in_hours(1)}, headers=headers)
    give_a_top3(client, headers)
    client.post("/api/top3/round/close", headers=headers)

    response = client.put(
        "/api/top3/round", json={"deadline": in_hours(24)}, headers=headers
    )

    assert response.json()["is_open"] is True
    assert choice_count(client) == 1


def test_a_new_round_clears_every_top3(client: TestClient):
    headers = ready_to_work(client, "superuser")
    client.put("/api/top3/round", json={"deadline": in_hours(1)}, headers=headers)
    give_a_top3(client, headers)
    deadline = in_hours(24 * 7)

    response = client.post(
        "/api/top3/round/new", json={"deadline": deadline}, headers=headers
    )

    assert response.status_code == 200, response.text
    assert response.json()["is_open"] is True
    assert same_moment(response.json()["deadline"], deadline)
    assert choice_count(client) == 0


# Access


def test_students_cannot_manage_choice_or_the_round(client: TestClient):
    teacher = ready_to_work(client, "teacher")
    project = create_project(client, teacher, "Smart Greenhouse")
    student = ready_to_work(client, "student")
    body = {"deadline": in_hours(1)}

    assert open_for_choice(client, student, project, True).status_code == 403
    assert client.get("/api/top3/round", headers=student).status_code == 403
    assert client.put("/api/top3/round", json=body, headers=student).status_code == 403
    assert client.post("/api/top3/round/close", headers=student).status_code == 403
    assert (
        client.post("/api/top3/round/new", json=body, headers=student).status_code
        == 403
    )
