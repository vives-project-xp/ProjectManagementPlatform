import pytest
from fastapi.testclient import TestClient

from tests.conftest import (
    add_member,
    create_project,
    create_student,
    ready_to_work,
    teacher_id,
)


def test_student_without_project_gets_nothing(client: TestClient):
    student = ready_to_work(client, "student")

    response = client.get("/api/my-project", headers=student)

    assert response.status_code == 200, response.text
    assert response.json() is None


def test_student_sees_own_project_with_product_owner_and_fellow_members(
    client: TestClient,
):
    superuser = ready_to_work(client, "superuser")
    student = ready_to_work(client, "student")
    me = client.get("/api/auth/me", headers=student).json()["id"]
    drone = create_project(client, superuser, "Drone")
    response = client.put(
        f"/api/projects/{drone}",
        json={
            "title": "Drone",
            "description": "Build a drone.",
            "product_owner_id": teacher_id(client, superuser),
            "team_size_min": 1,
            "team_size_max": 3,
        },
        headers=superuser,
    )
    assert response.status_code == 200, response.text
    add_member(client, superuser, drone, me)
    add_member(client, superuser, drone, create_student(client, superuser, "Lisa"))
    create_project(client, superuser, "Robot")

    response = client.get("/api/my-project", headers=student)

    assert response.status_code == 200, response.text
    assert response.json() == {
        "title": "Drone",
        "description": "Build a drone.",
        "product_owner": "Teacher Account",
        "fellow_members": ["Lisa Peeters"],
    }


@pytest.mark.parametrize("role", ["superuser", "teacher"])
def test_only_students_have_a_my_project(client: TestClient, role: str):
    headers = ready_to_work(client, role)

    assert client.get("/api/my-project", headers=headers).status_code == 403


def test_students_are_refused_other_projects_and_screens(client: TestClient):
    superuser = ready_to_work(client, "superuser")
    drone = create_project(client, superuser, "Drone")
    student = ready_to_work(client, "student")

    for path in [
        f"/api/projects/{drone}",
        "/api/projects",
        "/api/students",
        "/api/users",
        "/api/teachers",
    ]:
        assert client.get(path, headers=student).status_code == 403, path
