import pytest
from fastapi.testclient import TestClient

from tests.conftest import auth, ready_to_work

NEW_TEACHER = {
    "role": "teacher",
    "first_name": "Ann",
    "last_name": "Janssens",
    "email": "Ann.Janssens@vives.be",
    "temporary_password": "welcome-ann",
}
NEW_STUDENT = {
    "role": "student",
    "first_name": "Lisa",
    "last_name": "Peeters",
    "email": "lisa.peeters@student.vives.be",
    "temporary_password": "welcome-lisa",
    "programme": "Electronics-ICT",
    "year": "International",
}


def test_superuser_lists_all_users(client: TestClient):
    headers = ready_to_work(client, "superuser")

    response = client.get("/api/users", headers=headers)

    assert response.status_code == 200
    users = response.json()
    assert sorted(user["role"] for user in users) == ["student", "superuser", "teacher"]
    student = next(user for user in users if user["role"] == "student")
    assert student["programme"] == "Electronics-ICT"
    assert student["year"] == "1"
    assert student["is_active"] is True


def test_superuser_creates_a_teacher_who_must_change_their_password(
    client: TestClient,
):
    headers = ready_to_work(client, "superuser")

    response = client.post("/api/users", json=NEW_TEACHER, headers=headers)

    assert response.status_code == 201, response.text
    created = response.json()
    assert created["email"] == "ann.janssens@vives.be"
    assert created["role"] == "teacher"
    assert created["programme"] is None
    assert created["year"] is None
    login = client.post(
        "/api/auth/login",
        json={"email": "ann.janssens@vives.be", "password": "welcome-ann"},
    )
    assert login.status_code == 200
    assert login.json()["user"]["must_change_password"] is True
    listed = client.get("/api/users", headers=headers).json()
    assert "ann.janssens@vives.be" in [user["email"] for user in listed]


def test_superuser_creates_a_student_with_programme_and_year(client: TestClient):
    headers = ready_to_work(client, "superuser")

    response = client.post("/api/users", json=NEW_STUDENT, headers=headers)

    assert response.status_code == 201, response.text
    assert response.json()["programme"] == "Electronics-ICT"
    assert response.json()["year"] == "International"


@pytest.mark.parametrize(
    "changes",
    [
        {"programme": None},
        {"year": None},
        {"programme": "Chemistry"},
        {"year": "4"},
    ],
)
def test_student_needs_a_valid_programme_and_year(client: TestClient, changes: dict):
    headers = ready_to_work(client, "superuser")

    response = client.post("/api/users", json=NEW_STUDENT | changes, headers=headers)

    assert response.status_code == 422


def test_teacher_has_no_programme_or_year(client: TestClient):
    headers = ready_to_work(client, "superuser")
    teacher = NEW_TEACHER | {"programme": "Electronics-ICT", "year": "1"}

    response = client.post("/api/users", json=teacher, headers=headers)

    assert response.status_code == 422


@pytest.mark.parametrize(
    "changes",
    [
        {"role": "superuser"},
        {"temporary_password": "short"},
        {"first_name": " "},
        {"email": "not-an-email"},
    ],
)
def test_invalid_new_user_is_refused(client: TestClient, changes: dict):
    headers = ready_to_work(client, "superuser")

    response = client.post("/api/users", json=NEW_TEACHER | changes, headers=headers)

    assert response.status_code == 422


def test_duplicate_email_is_refused_case_insensitively(client: TestClient):
    headers = ready_to_work(client, "superuser")
    client.post("/api/users", json=NEW_TEACHER, headers=headers)

    response = client.post(
        "/api/users",
        json=NEW_STUDENT | {"email": "ANN.JANSSENS@vives.be"},
        headers=headers,
    )

    assert response.status_code == 409
    assert "ann.janssens@vives.be is already in use" in response.json()["detail"]


@pytest.mark.parametrize("role", ["teacher", "student"])
def test_only_the_superuser_manages_users(client: TestClient, role: str):
    headers = ready_to_work(client, role)

    listed = client.get("/api/users", headers=headers)
    created = client.post("/api/users", json=NEW_TEACHER, headers=headers)

    assert listed.status_code == 403
    assert created.status_code == 403


def test_users_api_needs_a_login(client: TestClient):
    assert client.get("/api/users").status_code == 401
    assert client.get("/api/users", headers=auth("not-a-token")).status_code == 401


def test_programmes_come_from_the_backend(client: TestClient):
    headers = ready_to_work(client, "superuser")

    response = client.get("/api/programmes", headers=headers)

    assert response.status_code == 200
    assert [p["name"] for p in response.json()] == ["Electronics-ICT"]
