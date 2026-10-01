import pytest
from fastapi.testclient import TestClient

from tests.conftest import (
    NEW_STUDENT,
    add_member,
    create_project,
    create_student,
    ready_to_work,
)


def programme_names(client: TestClient, headers: dict[str, str]) -> list[str]:
    response = client.get("/api/programmes", headers=headers)
    assert response.status_code == 200, response.text
    return [programme["name"] for programme in response.json()]


def programme_id(client: TestClient, headers: dict[str, str], name: str) -> int:
    programmes = client.get("/api/programmes", headers=headers).json()
    return next(p["id"] for p in programmes if p["name"] == name)


def add_programme(client: TestClient, headers: dict[str, str], name: str):
    return client.post("/api/programmes", json={"name": name}, headers=headers)


@pytest.fixture
def superuser(client: TestClient) -> dict[str, str]:
    return ready_to_work(client, "superuser")


def test_electronics_ict_is_in_the_list_from_the_start(client: TestClient):
    teacher = ready_to_work(client, "teacher")

    assert programme_names(client, teacher) == ["Electronics-ICT"]


def test_superuser_adds_a_programme_that_is_usable_at_once(
    client: TestClient, superuser: dict[str, str]
):
    response = add_programme(client, superuser, "  Mechanical Engineering ")

    assert response.status_code == 201, response.text
    assert response.json()["name"] == "Mechanical Engineering"
    assert programme_names(client, superuser) == [
        "Electronics-ICT",
        "Mechanical Engineering",
    ]
    student = client.post(
        "/api/users",
        json=NEW_STUDENT
        | {
            "first_name": "Lisa",
            "email": "lisa@student.vives.be",
            "programme": "Mechanical Engineering",
        },
        headers=superuser,
    )
    assert student.status_code == 201, student.text
    filtered = client.get(
        "/api/students?programme=Mechanical Engineering", headers=superuser
    ).json()
    assert [s["name"] for s in filtered] == ["Lisa Peeters"]


@pytest.mark.parametrize(
    ("name", "status"),
    [("", 422), ("   ", 422), ("Electronics-ICT", 409), (" electronics-ict ", 409)],
)
def test_empty_and_duplicate_programmes_are_refused(
    client: TestClient, superuser: dict[str, str], name: str, status: int
):
    assert add_programme(client, superuser, name).status_code == status
    assert programme_names(client, superuser) == ["Electronics-ICT"]


def test_a_student_gets_the_programme_as_it_is_spelled_in_the_list(
    client: TestClient, superuser: dict[str, str]
):
    response = client.post(
        "/api/users",
        json=NEW_STUDENT
        | {
            "first_name": "Lisa",
            "email": "lisa@student.vives.be",
            "programme": "electronics-ict",
        },
        headers=superuser,
    )

    assert response.status_code == 201, response.text
    assert response.json()["programme"] == "Electronics-ICT"


def test_rename_updates_users_but_not_makers(
    client: TestClient, superuser: dict[str, str]
):
    drone = create_project(client, superuser, "Drone")
    add_member(client, superuser, drone, create_student(client, superuser, "Lisa"))
    archived = client.post(f"/api/projects/{drone}/archive", headers=superuser)
    assert archived.status_code == 200, archived.text

    response = client.put(
        f"/api/programmes/{programme_id(client, superuser, 'Electronics-ICT')}",
        json={"name": "Elektronica-ICT"},
        headers=superuser,
    )

    assert response.status_code == 200, response.text
    assert response.json()["name"] == "Elektronica-ICT"
    assert programme_names(client, superuser) == ["Elektronica-ICT"]
    students = client.get("/api/students", headers=superuser).json()
    assert {s["programme"] for s in students} == {"Elektronica-ICT"}
    project = client.get(f"/api/projects/{drone}", headers=superuser).json()
    assert [maker["programme"] for maker in project["makers"]] == ["Electronics-ICT"]


def test_rename_to_another_programmes_name_is_refused(
    client: TestClient, superuser: dict[str, str]
):
    add_programme(client, superuser, "Chemistry")
    chemistry = programme_id(client, superuser, "Chemistry")

    duplicate = client.put(
        f"/api/programmes/{chemistry}",
        json={"name": "ELECTRONICS-ICT"},
        headers=superuser,
    )
    respelled = client.put(
        f"/api/programmes/{chemistry}", json={"name": "CHEMISTRY"}, headers=superuser
    )

    assert duplicate.status_code == 409
    assert respelled.status_code == 200, respelled.text
    assert programme_names(client, superuser) == ["CHEMISTRY", "Electronics-ICT"]


def test_superuser_removes_a_programme_nobody_has(
    client: TestClient, superuser: dict[str, str]
):
    add_programme(client, superuser, "Chemistry")

    response = client.delete(
        f"/api/programmes/{programme_id(client, superuser, 'Chemistry')}",
        headers=superuser,
    )

    assert response.status_code == 204, response.text
    assert programme_names(client, superuser) == ["Electronics-ICT"]


def test_removing_a_programme_a_user_has_is_refused(
    client: TestClient, superuser: dict[str, str]
):
    response = client.delete(
        f"/api/programmes/{programme_id(client, superuser, 'Electronics-ICT')}",
        headers=superuser,
    )

    assert response.status_code == 409
    assert "Student Account" not in response.json()["detail"]
    assert "1 User" in response.json()["detail"]
    assert programme_names(client, superuser) == ["Electronics-ICT"]


def test_unknown_programmes_are_not_found(
    client: TestClient, superuser: dict[str, str]
):
    assert (
        client.put(
            "/api/programmes/999", json={"name": "X"}, headers=superuser
        ).status_code
        == 404
    )
    assert client.delete("/api/programmes/999", headers=superuser).status_code == 404


def test_filtering_students_on_an_unknown_programme_is_refused(
    client: TestClient, superuser: dict[str, str]
):
    assert (
        client.get("/api/students?programme=Chemistry", headers=superuser).status_code
        == 422
    )


@pytest.mark.parametrize("role", ["teacher", "student"])
def test_only_the_superuser_manages_programmes(client: TestClient, role: str):
    superuser = ready_to_work(client, "superuser")
    electronics = programme_id(client, superuser, "Electronics-ICT")
    headers = ready_to_work(client, role)

    assert add_programme(client, headers, "Chemistry").status_code == 403
    assert (
        client.put(
            f"/api/programmes/{electronics}", json={"name": "X"}, headers=headers
        ).status_code
        == 403
    )
    assert (
        client.delete(f"/api/programmes/{electronics}", headers=headers).status_code
        == 403
    )
