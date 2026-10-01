import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update

from pmp_backend.models import User
from tests.conftest import auth, ready_to_work


def teacher_id(client: TestClient, headers: dict[str, str]) -> int:
    teachers = client.get("/api/teachers", headers=headers).json()
    return next(t["id"] for t in teachers if t["name"] == "Teacher Account")


def new_project(client: TestClient, headers: dict[str, str], **changes) -> dict:
    return {
        "title": "Smart Greenhouse",
        "description": "Sensors and a dashboard for the campus greenhouse.",
        "product_owner_id": teacher_id(client, headers),
        "team_size_min": 4,
        "team_size_max": 6,
    } | changes


def test_teacher_creates_and_lists_a_project(client: TestClient):
    headers = ready_to_work(client, "teacher")

    response = client.post(
        "/api/projects", json=new_project(client, headers), headers=headers
    )

    assert response.status_code == 201, response.text
    created = response.json()
    assert created["title"] == "Smart Greenhouse"
    assert created["product_owner"]["name"] == "Teacher Account"
    assert created["team_size_min"] == 4
    assert created["team_size_max"] == 6
    assert created["status"] == "active"
    listed = client.get("/api/projects", headers=headers).json()
    assert [project["title"] for project in listed] == ["Smart Greenhouse"]


def test_superuser_manages_projects_too(client: TestClient):
    headers = ready_to_work(client, "superuser")

    response = client.post(
        "/api/projects", json=new_project(client, headers), headers=headers
    )

    assert response.status_code == 201, response.text


def test_description_is_optional(client: TestClient):
    headers = ready_to_work(client, "teacher")

    response = client.post(
        "/api/projects",
        json=new_project(client, headers, description=None),
        headers=headers,
    )

    assert response.status_code == 201
    assert response.json()["description"] is None


def test_any_teacher_edits_any_project(client: TestClient):
    headers = ready_to_work(client, "teacher")
    created = client.post(
        "/api/projects", json=new_project(client, headers), headers=headers
    ).json()

    response = client.put(
        f"/api/projects/{created['id']}",
        json=new_project(
            client, headers, title="Greenhouse 2.0", description="", team_size_max=5
        ),
        headers=headers,
    )

    assert response.status_code == 200, response.text
    details = client.get(f"/api/projects/{created['id']}", headers=headers).json()
    assert details["title"] == "Greenhouse 2.0"
    assert details["description"] is None
    assert details["team_size_max"] == 5


def test_title_is_unique_case_insensitively(client: TestClient):
    headers = ready_to_work(client, "teacher")
    client.post("/api/projects", json=new_project(client, headers), headers=headers)

    response = client.post(
        "/api/projects",
        json=new_project(client, headers, title="  SMART greenhouse "),
        headers=headers,
    )

    assert response.status_code == 409
    assert "Smart Greenhouse" in response.json()["detail"]


def test_renaming_to_a_taken_title_is_refused(client: TestClient):
    headers = ready_to_work(client, "teacher")
    client.post("/api/projects", json=new_project(client, headers), headers=headers)
    other = client.post(
        "/api/projects",
        json=new_project(client, headers, title="Drone"),
        headers=headers,
    ).json()

    response = client.put(
        f"/api/projects/{other['id']}",
        json=new_project(client, headers, title="smart greenhouse"),
        headers=headers,
    )

    assert response.status_code == 409


def test_keeping_the_own_title_on_edit_is_fine(client: TestClient):
    headers = ready_to_work(client, "teacher")
    created = client.post(
        "/api/projects", json=new_project(client, headers), headers=headers
    ).json()

    response = client.put(
        f"/api/projects/{created['id']}",
        json=new_project(client, headers, title="SMART GREENHOUSE"),
        headers=headers,
    )

    assert response.status_code == 200


@pytest.mark.parametrize(
    "changes",
    [
        {"title": "   "},
        {"team_size_min": 0},
        {"team_size_min": 5, "team_size_max": 4},
        {"team_size_max": None},
    ],
)
def test_invalid_project_is_refused(client: TestClient, changes: dict):
    headers = ready_to_work(client, "teacher")

    response = client.post(
        "/api/projects", json=new_project(client, headers, **changes), headers=headers
    )

    assert response.status_code == 422


def test_product_owner_must_be_an_active_teacher(client: TestClient):
    headers = ready_to_work(client, "teacher")
    users = client.app.state.sessionmaker
    with users() as session:
        superuser_id = session.query(User.id).filter_by(role="superuser").scalar()
        student_id = session.query(User.id).filter_by(role="student").scalar()

    for owner_id in (superuser_id, student_id, 9999):
        response = client.post(
            "/api/projects",
            json=new_project(client, headers, product_owner_id=owner_id),
            headers=headers,
        )
        assert response.status_code == 422, owner_id
        assert (
            response.json()["detail"] == "The Product Owner must be an active Teacher."
        )


def test_deactivated_teacher_cannot_become_product_owner(client: TestClient):
    headers = ready_to_work(client, "superuser")
    owner_id = teacher_id(client, headers)
    with client.app.state.sessionmaker() as session:
        session.execute(update(User).where(User.id == owner_id).values(is_active=False))
        session.commit()

    response = client.post(
        "/api/projects",
        json={
            "title": "Drone",
            "product_owner_id": owner_id,
            "team_size_min": 1,
            "team_size_max": 2,
        },
        headers=headers,
    )

    assert response.status_code == 422
    teachers = client.get("/api/teachers", headers=headers).json()
    assert owner_id not in [teacher["id"] for teacher in teachers]


def test_unknown_project_is_not_found(client: TestClient):
    headers = ready_to_work(client, "teacher")

    assert client.get("/api/projects/9999", headers=headers).status_code == 404


def test_students_cannot_use_projects_or_teachers(client: TestClient):
    teacher = ready_to_work(client, "teacher")
    created = client.post(
        "/api/projects", json=new_project(client, teacher), headers=teacher
    ).json()
    student = ready_to_work(client, "student")

    assert client.get("/api/projects", headers=student).status_code == 403
    assert (
        client.get(f"/api/projects/{created['id']}", headers=student).status_code == 403
    )
    assert client.post("/api/projects", json={}, headers=student).status_code == 403
    assert (
        client.put(
            f"/api/projects/{created['id']}", json={}, headers=student
        ).status_code
        == 403
    )
    assert client.get("/api/teachers", headers=student).status_code == 403


def test_projects_api_needs_a_login(client: TestClient):
    assert client.get("/api/projects", headers=auth("not-a-token")).status_code == 401
