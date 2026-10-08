from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, update

from pmp_backend.models import Top3Round
from tests.conftest import add_member, create_project, ready_to_work

JPG = b"\xff\xd8\xff\xe0" + b"jpg-body" * 10


def in_hours(hours: float) -> str:
    return (datetime.now(UTC) + timedelta(hours=hours)).isoformat()


def open_projects(client: TestClient, staff, *titles: str) -> list[int]:
    ids = []
    for title in titles:
        project = create_project(client, staff, title)
        client.put(
            f"/api/projects/{project}/open-for-choice",
            json={"open": True},
            headers=staff,
        )
        ids.append(project)
    return ids


def open_round(client: TestClient, staff) -> None:
    response = client.put(
        "/api/top3/round", json={"deadline": in_hours(24)}, headers=staff
    )
    assert response.status_code == 200, response.text


def submit(client: TestClient, student, project_ids: list[int]):
    return client.post(
        "/api/my-top3", json={"project_ids": project_ids}, headers=student
    )


@pytest.fixture
def staff(client: TestClient) -> dict[str, str]:
    return ready_to_work(client, "superuser")


@pytest.fixture
def student(client: TestClient, staff) -> dict[str, str]:
    return ready_to_work(client, "student")


# Seeing the choice


def test_before_a_round_there_is_nothing_to_choose(client: TestClient, student):
    response = client.get("/api/my-top3", headers=student)

    assert response.status_code == 200
    body = response.json()
    assert body["round"] == {"deadline": None, "is_open": False}
    assert body["top3"] is None
    assert body["can_submit"] is False


def test_student_sees_the_open_projects_while_the_round_is_open(
    client: TestClient, staff, student
):
    greenhouse, drone, _ = open_projects(
        client, staff, "Smart Greenhouse", "Drone", "Robot"
    )
    create_project(client, staff, "Not open")
    client.put(
        f"/api/projects/{drone}/photo",
        files={"photo": ("a.jpg", JPG, "image/jpeg")},
        headers=staff,
    )
    open_round(client, staff)

    body = client.get("/api/my-top3", headers=student).json()

    assert body["round"]["is_open"] is True
    assert body["can_submit"] is True
    assert body["places"] == 3
    assert [p["title"] for p in body["projects"]] == [
        "Drone",
        "Robot",
        "Smart Greenhouse",
    ]
    first = body["projects"][0]
    assert first["product_owner"] == "Teacher Account"
    assert first["team_size_min"] == 1
    assert first["photo_version"] == 1
    # Never how popular a Project is.
    assert "choices" not in first and "count" not in first
    # And the Student may see the photo of a Project open for choice.
    photo = client.get(f"/api/projects/{drone}/photo", headers=student)
    assert photo.status_code == 200
    assert client.get(f"/api/projects/{greenhouse}", headers=student).status_code == 403


def test_with_fewer_open_projects_there_are_fewer_places(
    client: TestClient, staff, student
):
    open_projects(client, staff, "Smart Greenhouse", "Drone")
    open_round(client, staff)

    assert client.get("/api/my-top3", headers=student).json()["places"] == 2


# Submitting


def test_student_submits_a_ranked_top3_once(client: TestClient, staff, student):
    greenhouse, drone, robot = open_projects(
        client, staff, "Smart Greenhouse", "Drone", "Robot"
    )
    open_round(client, staff)

    response = submit(client, student, [drone, robot, greenhouse])

    assert response.status_code == 200, response.text
    body = client.get("/api/my-top3", headers=student).json()
    assert [(c["rank"], c["title"], c["available"]) for c in body["top3"]] == [
        (1, "Drone", True),
        (2, "Robot", True),
        (3, "Smart Greenhouse", True),
    ]
    assert body["submitted_at"] is not None
    assert body["can_submit"] is False
    again = submit(client, student, [greenhouse, drone, robot])
    assert again.status_code == 409
    assert again.json()["detail"] == "You already submitted your Top 3."


@pytest.mark.parametrize(
    ("choose", "message"),
    [
        (lambda ids: ids[:2], "Choose 3 different Projects."),
        (lambda ids: [ids[0], ids[0], ids[1]], "Choose each Project only once."),
        (lambda ids: [ids[0], ids[1], ids[3]], "Not open is not open for choice."),
        (lambda ids: [ids[0], ids[1], 9999], "That Project is not open for choice."),
    ],
)
def test_an_invalid_top3_is_refused(
    client: TestClient, staff, student, choose, message: str
):
    ids = open_projects(client, staff, "Smart Greenhouse", "Drone", "Robot")
    ids.append(create_project(client, staff, "Not open"))
    open_round(client, staff)

    response = submit(client, student, choose(ids))

    assert response.status_code == 422
    assert response.json()["detail"] == message
    assert client.get("/api/my-top3", headers=student).json()["top3"] is None


def test_submitting_needs_an_open_round(client: TestClient, staff, student):
    ids = open_projects(client, staff, "Smart Greenhouse", "Drone", "Robot")

    before = submit(client, student, ids)
    open_round(client, staff)
    with client.app.state.sessionmaker() as session:
        session.execute(
            update(Top3Round).values(deadline=func.now() - timedelta(minutes=1))
        )
        session.commit()
    after = submit(client, student, ids)

    for response in (before, after):
        assert response.status_code == 409
        assert response.json()["detail"] == "The Top 3 round is not open."


def test_a_member_cannot_submit(client: TestClient, staff, student):
    ids = open_projects(client, staff, "Smart Greenhouse", "Drone", "Robot")
    open_round(client, staff)
    me = client.get("/api/auth/me", headers=student).json()["id"]
    add_member(client, staff, ids[0], me)

    body = client.get("/api/my-top3", headers=student).json()
    response = submit(client, student, ids)

    assert body["can_submit"] is False
    assert response.status_code == 409
    assert response.json()["detail"] == "You already have a Project."


def test_a_closed_project_shows_as_no_longer_available(
    client: TestClient, staff, student
):
    greenhouse, drone, robot = open_projects(
        client, staff, "Smart Greenhouse", "Drone", "Robot"
    )
    open_round(client, staff)
    submit(client, student, [drone, robot, greenhouse])

    client.put(
        f"/api/projects/{robot}/open-for-choice", json={"open": False}, headers=staff
    )
    client.delete(f"/api/projects/{greenhouse}", headers=staff)

    top3 = client.get("/api/my-top3", headers=student).json()["top3"]
    assert [(c["rank"], c["title"], c["available"]) for c in top3] == [
        (1, "Drone", True),
        (2, "Robot", False),
        (3, None, False),
    ]


# Access


@pytest.mark.parametrize("role", ["teacher", "superuser"])
def test_staff_cannot_submit(client: TestClient, role: str):
    headers = ready_to_work(client, role)

    assert client.get("/api/my-top3", headers=headers).status_code == 403
    assert submit(client, headers, [1, 2, 3]).status_code == 403
