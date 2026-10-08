import pytest
from fastapi.testclient import TestClient

from pmp_backend.app import create_app
from pmp_backend.settings import Settings
from tests.conftest import (
    STARTING_ACCOUNTS,
    add_member,
    auth,
    create_project,
    ready_to_work,
)

NEW_STUDENT = {
    "role": "student",
    "first_name": "Lisa",
    "last_name": "Peeters",
    "email": "lisa.peeters@student.vives.be",
    "temporary_password": "welcome-lisa",
    "programme": "Electronics-ICT",
    "year": "1",
}


def user_id(client: TestClient, headers: dict[str, str], email: str) -> int:
    users = client.get("/api/users", headers=headers).json()
    return next(user["id"] for user in users if user["email"] == email)


def create_student(client: TestClient, headers: dict[str, str]) -> int:
    response = client.post("/api/users", json=NEW_STUDENT, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def edit_body(**changes) -> dict:
    return {
        "first_name": "Lisa",
        "last_name": "Peeters-Janssens",
        "email": "lisa.pj@student.vives.be",
        "programme": "Electronics-ICT",
        "year": "2",
    } | changes


# Editing


def test_superuser_edits_a_student(client: TestClient):
    headers = ready_to_work(client, "superuser")
    student = create_student(client, headers)

    response = client.put(f"/api/users/{student}", json=edit_body(), headers=headers)

    assert response.status_code == 200, response.text
    edited = client.get(f"/api/users/{student}", headers=headers).json()
    assert edited["last_name"] == "Peeters-Janssens"
    assert edited["email"] == "lisa.pj@student.vives.be"
    assert edited["year"] == "2"
    assert edited["role"] == "student"


def test_role_cannot_be_changed(client: TestClient):
    headers = ready_to_work(client, "superuser")
    student = create_student(client, headers)

    response = client.put(
        f"/api/users/{student}", json=edit_body(role="teacher"), headers=headers
    )

    assert response.status_code == 422
    assert client.get(f"/api/users/{student}", headers=headers).json()["role"] == (
        "student"
    )


def test_editing_to_a_used_email_is_refused(client: TestClient):
    headers = ready_to_work(client, "superuser")
    student = create_student(client, headers)

    response = client.put(
        f"/api/users/{student}",
        json=edit_body(email="Teacher@PMP.local"),
        headers=headers,
    )

    assert response.status_code == 409
    assert "teacher@pmp.local is already in use" in response.json()["detail"]


def test_keeping_the_own_email_is_fine(client: TestClient):
    headers = ready_to_work(client, "superuser")
    student = create_student(client, headers)

    response = client.put(
        f"/api/users/{student}",
        json=edit_body(email="LISA.PEETERS@student.vives.be"),
        headers=headers,
    )

    assert response.status_code == 200


def test_edited_student_keeps_programme_and_year_rules(client: TestClient):
    headers = ready_to_work(client, "superuser")
    student = create_student(client, headers)
    teacher = user_id(client, headers, "teacher@pmp.local")

    no_year = client.put(
        f"/api/users/{student}", json=edit_body(year=None), headers=headers
    )
    teacher_with_year = client.put(
        f"/api/users/{teacher}",
        json=edit_body(email="teacher@pmp.local"),
        headers=headers,
    )

    assert no_year.status_code == 422
    assert teacher_with_year.status_code == 422


def test_unknown_user_is_not_found(client: TestClient):
    headers = ready_to_work(client, "superuser")

    assert client.get("/api/users/9999", headers=headers).status_code == 404
    assert (
        client.put("/api/users/9999", json=edit_body(), headers=headers).status_code
        == 404
    )


# Deactivating


def test_deactivated_user_is_refused_and_loses_their_session(client: TestClient):
    headers = ready_to_work(client, "superuser")
    teacher_headers = ready_to_work(client, "teacher")
    teacher = user_id(client, headers, "teacher@pmp.local")

    response = client.post(f"/api/users/{teacher}/deactivate", headers=headers)

    assert response.status_code == 200, response.text
    assert response.json()["is_active"] is False
    assert client.get("/api/auth/me", headers=teacher_headers).status_code == 401
    relogin = client.post(
        "/api/auth/login",
        json={"email": "teacher@pmp.local", "password": "teacher-secret-1-changed"},
    )
    assert relogin.status_code == 401


def test_reactivated_user_can_log_in_again(client: TestClient):
    headers = ready_to_work(client, "superuser")
    ready_to_work(client, "teacher")
    teacher = user_id(client, headers, "teacher@pmp.local")
    client.post(f"/api/users/{teacher}/deactivate", headers=headers)

    response = client.post(f"/api/users/{teacher}/reactivate", headers=headers)

    assert response.status_code == 200
    assert response.json()["is_active"] is True
    relogin = client.post(
        "/api/auth/login",
        json={"email": "teacher@pmp.local", "password": "teacher-secret-1-changed"},
    )
    assert relogin.status_code == 200


def test_deactivating_yourself_is_refused(client: TestClient):
    headers = ready_to_work(client, "superuser")
    me = client.get("/api/auth/me", headers=headers).json()["id"]

    response = client.post(f"/api/users/{me}/deactivate", headers=headers)

    assert response.status_code == 409
    assert response.json()["detail"] == "You cannot deactivate yourself."


def test_product_owner_of_an_active_project_cannot_be_deactivated(
    client: TestClient,
):
    headers = ready_to_work(client, "superuser")
    teacher = user_id(client, headers, "teacher@pmp.local")
    for title in ("Smart Greenhouse", "Drone"):
        created = client.post(
            "/api/projects",
            json={
                "title": title,
                "product_owner_id": teacher,
                "team_size_min": 1,
                "team_size_max": 3,
            },
            headers=headers,
        )
        assert created.status_code == 201, created.text

    response = client.post(f"/api/users/{teacher}/deactivate", headers=headers)

    assert response.status_code == 409
    assert "Drone" in response.json()["detail"]
    assert "Smart Greenhouse" in response.json()["detail"]


# Deleting


def test_superuser_deletes_a_student_without_links(client: TestClient):
    headers = ready_to_work(client, "superuser")
    student = create_student(client, headers)

    response = client.delete(f"/api/users/{student}", headers=headers)

    assert response.status_code == 204, response.text
    assert client.get(f"/api/users/{student}", headers=headers).status_code == 404
    again = client.post("/api/users", json=NEW_STUDENT, headers=headers)
    assert again.status_code == 201, again.text


def test_deleted_user_loses_their_session(client: TestClient):
    headers = ready_to_work(client, "superuser")
    teacher_headers = ready_to_work(client, "teacher")
    teacher = user_id(client, headers, "teacher@pmp.local")

    response = client.delete(f"/api/users/{teacher}", headers=headers)

    assert response.status_code == 204, response.text
    assert client.get("/api/auth/me", headers=teacher_headers).status_code == 401


def test_deactivated_user_without_links_can_be_deleted(client: TestClient):
    headers = ready_to_work(client, "superuser")
    student = create_student(client, headers)
    client.post(f"/api/users/{student}/deactivate", headers=headers)

    response = client.delete(f"/api/users/{student}", headers=headers)

    assert response.status_code == 204, response.text


def test_the_superuser_cannot_be_deleted(client: TestClient):
    headers = ready_to_work(client, "superuser")
    me = client.get("/api/auth/me", headers=headers).json()["id"]

    response = client.delete(f"/api/users/{me}", headers=headers)

    assert response.status_code == 409
    assert response.json()["detail"] == "The Superuser cannot be deleted."


def test_a_member_cannot_be_deleted(client: TestClient):
    headers = ready_to_work(client, "superuser")
    student = create_student(client, headers)
    project = create_project(client, headers, "Smart Greenhouse")
    add_member(client, headers, project, student)

    response = client.delete(f"/api/users/{student}", headers=headers)

    assert response.status_code == 409
    assert "Member of Smart Greenhouse" in response.json()["detail"]
    assert "Deactivate" in response.json()["detail"]


def test_a_student_in_makers_cannot_be_deleted(client: TestClient):
    headers = ready_to_work(client, "superuser")
    student = create_student(client, headers)
    project = create_project(client, headers, "Smart Greenhouse")
    add_member(client, headers, project, student)
    client.post(f"/api/projects/{project}/archive", headers=headers)

    response = client.delete(f"/api/users/{student}", headers=headers)

    assert response.status_code == 409
    assert "Makers of Smart Greenhouse" in response.json()["detail"]
    assert "Deactivate" in response.json()["detail"]


@pytest.mark.parametrize("archived", [False, True])
def test_a_product_owner_cannot_be_deleted(client: TestClient, archived: bool):
    headers = ready_to_work(client, "superuser")
    teacher = user_id(client, headers, "teacher@pmp.local")
    project = create_project(client, headers, "Smart Greenhouse")
    if archived:
        client.post(f"/api/projects/{project}/archive", headers=headers)

    response = client.delete(f"/api/users/{teacher}", headers=headers)

    assert response.status_code == 409
    assert "Product Owner of Smart Greenhouse" in response.json()["detail"]
    assert "Deactivate" in response.json()["detail"]


def test_deleting_an_unknown_user_is_not_found(client: TestClient):
    headers = ready_to_work(client, "superuser")

    assert client.delete("/api/users/9999", headers=headers).status_code == 404


# Resetting a password


def test_reset_password_forces_a_change_at_next_login(client: TestClient):
    headers = ready_to_work(client, "superuser")
    ready_to_work(client, "student")
    student = user_id(client, headers, "student@pmp.local")

    response = client.post(
        f"/api/users/{student}/reset-password",
        json={"temporary_password": "fresh-start-1"},
        headers=headers,
    )

    assert response.status_code == 204, response.text
    old = client.post(
        "/api/auth/login",
        json={"email": "student@pmp.local", "password": "student-secret-1-changed"},
    )
    new = client.post(
        "/api/auth/login",
        json={"email": "student@pmp.local", "password": "fresh-start-1"},
    )
    assert old.status_code == 401
    assert new.status_code == 200
    assert new.json()["user"]["must_change_password"] is True


def test_reset_password_needs_eight_characters(client: TestClient):
    headers = ready_to_work(client, "superuser")
    student = user_id(client, headers, "student@pmp.local")

    response = client.post(
        f"/api/users/{student}/reset-password",
        json={"temporary_password": "short"},
        headers=headers,
    )

    assert response.status_code == 422


# Filters


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("role=teacher", ["teacher@pmp.local"]),
        ("active=false", ["student@pmp.local"]),
        ("role=student&active=true", ["lisa.peeters@student.vives.be"]),
    ],
)
def test_users_can_be_filtered_on_role_and_active(
    client: TestClient, query: str, expected: list[str]
):
    headers = ready_to_work(client, "superuser")
    create_student(client, headers)
    student = user_id(client, headers, "student@pmp.local")
    client.post(f"/api/users/{student}/deactivate", headers=headers)

    response = client.get(f"/api/users?{query}", headers=headers)

    assert response.status_code == 200
    assert [user["email"] for user in response.json()] == expected


# Access


@pytest.mark.parametrize("role", ["teacher", "student"])
def test_only_the_superuser_edits_deactivates_resets_and_deletes(
    client: TestClient, role: str
):
    headers = ready_to_work(client, role)
    target = client.get("/api/auth/me", headers=headers).json()["id"]

    for method, path, body in [
        ("GET", f"/api/users/{target}", None),
        ("PUT", f"/api/users/{target}", edit_body()),
        ("POST", f"/api/users/{target}/deactivate", None),
        ("POST", f"/api/users/{target}/reactivate", None),
        ("DELETE", f"/api/users/{target}", None),
        (
            "POST",
            f"/api/users/{target}/reset-password",
            {"temporary_password": "x" * 8},
        ),
    ]:
        response = client.request(method, path, json=body, headers=headers)
        assert response.status_code == 403, (method, path)


# Starting accounts


def test_edited_starting_account_is_not_created_again(settings: Settings):
    with TestClient(create_app(settings)) as client:
        headers = ready_to_work(client, "superuser")
        teacher = user_id(client, headers, "teacher@pmp.local")
        client.put(
            f"/api/users/{teacher}",
            json=edit_body(
                first_name="Ann",
                last_name="Janssens",
                email="ann.janssens@vives.be",
                programme=None,
                year=None,
            ),
            headers=headers,
        )

    # A restart (redeploy) reads the same logins.txt with the old email.
    with TestClient(create_app(settings)) as client:
        email, password = STARTING_ACCOUNTS["teacher"]
        response = client.post(
            "/api/auth/login", json={"email": email, "password": password}
        )

        assert response.status_code == 401


def test_deleted_starting_account_is_not_created_again(settings: Settings):
    with TestClient(create_app(settings)) as client:
        headers = ready_to_work(client, "superuser")
        teacher = user_id(client, headers, "teacher@pmp.local")
        deleted = client.delete(f"/api/users/{teacher}", headers=headers)
        assert deleted.status_code == 204, deleted.text

    # A restart (redeploy) reads the same logins.txt, but Users already exist.
    with TestClient(create_app(settings)) as client:
        email, password = STARTING_ACCOUNTS["teacher"]
        response = client.post(
            "/api/auth/login", json={"email": email, "password": password}
        )

        assert response.status_code == 401


def test_users_api_needs_a_login(client: TestClient):
    assert client.get("/api/users/1", headers=auth("not-a-token")).status_code == 401
