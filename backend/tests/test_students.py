import pytest
from fastapi.testclient import TestClient

from tests.conftest import add_member, create_project, create_student, ready_to_work


@pytest.fixture
def superuser(client: TestClient) -> dict[str, str]:
    """A Superuser with three Students: Lisa (year 2, in Drone), Tom (year 2) and
    the starting Student account (year 1)."""
    superuser = ready_to_work(client, "superuser")
    drone = create_project(client, superuser, "Drone")
    add_member(client, superuser, drone, create_student(client, superuser, "Lisa"))
    create_student(client, superuser, "Tom")
    return superuser


def names(client: TestClient, headers: dict[str, str], query: str = "") -> list[str]:
    response = client.get(f"/api/students{query}", headers=headers)
    assert response.status_code == 200, response.text
    return [student["name"] for student in response.json()]


def test_all_students_are_listed_with_their_project(
    client: TestClient, superuser: dict[str, str]
):
    students = client.get("/api/students", headers=superuser).json()

    assert [
        (s["name"], s["programme"], s["year"], (s["project"] or {}).get("title"))
        for s in students
    ] == [
        ("Student Account", "Electronics-ICT", "1", None),
        ("Lisa Peeters", "Electronics-ICT", "2", "Drone"),
        ("Tom Peeters", "Electronics-ICT", "2", None),
    ]


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("?without_project=true", ["Student Account", "Tom Peeters"]),
        ("?year=2", ["Lisa Peeters", "Tom Peeters"]),
        (
            "?programme=Electronics-ICT",
            ["Student Account", "Lisa Peeters", "Tom Peeters"],
        ),
        ("?programme=Electronics-ICT&year=1", ["Student Account"]),
        ("?without_project=true&year=2", ["Tom Peeters"]),
    ],
)
def test_students_can_be_filtered(
    client: TestClient, superuser: dict[str, str], query: str, expected: list[str]
):
    assert names(client, superuser, query) == expected


def test_unknown_filter_values_are_refused(
    client: TestClient, superuser: dict[str, str]
):
    assert client.get("/api/students?year=4", headers=superuser).status_code == 422


def test_teachers_can_read_the_students_list(client: TestClient):
    teacher = ready_to_work(client, "teacher")

    assert names(client, teacher) == ["Student Account"]


def test_students_cannot_read_the_students_list(client: TestClient):
    student = ready_to_work(client, "student")

    assert client.get("/api/students", headers=student).status_code == 403
