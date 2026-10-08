from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pmp_backend import testing
from pmp_backend.app import create_app
from pmp_backend.settings import Settings

# Tests run against a real PostgreSQL (docs/coding-standards.md). Locally that is
# the database from compose.test.yml; in CI a PostgreSQL service container.
TEST_DATABASE_URL = testing.TEST_DATABASE_URL
TEST_JWT_SECRET = "test-secret-that-is-long-enough-for-hs256-signing"

STARTING_ACCOUNTS = {
    "superuser": ("superuser@pmp.local", "super-secret-1"),
    "teacher": ("teacher@pmp.local", "teacher-secret-1"),
    "student": ("student@pmp.local", "student-secret-1"),
}


@pytest.fixture(scope="session", autouse=True)
def _migrated_database() -> None:
    testing.migrate(TEST_DATABASE_URL)


@pytest.fixture(autouse=True)
def _clean_database() -> None:
    testing.reset(TEST_DATABASE_URL)


@pytest.fixture
def logins_file(tmp_path: Path) -> Path:
    path = tmp_path / "logins.txt"
    lines = ["# role,email,password"]
    lines += [f"{role},{email},{pw}" for role, (email, pw) in STARTING_ACCOUNTS.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


@pytest.fixture
def settings(logins_file: Path, tmp_path: Path) -> Settings:
    return Settings(
        database_url=TEST_DATABASE_URL,
        jwt_secret=TEST_JWT_SECRET,
        logins_file=logins_file,
        photos_dir=tmp_path / "photos",
    )


@pytest.fixture
def github() -> testing.FakeGitHub:
    return testing.FakeGitHub()


@pytest.fixture
def client(settings: Settings, github: testing.FakeGitHub) -> Iterator[TestClient]:
    app = create_app(settings)
    app.state.github = github
    # Entering the client runs the app's startup, which creates the starting accounts.
    with TestClient(app) as client:
        yield client


def login(client: TestClient, role: str) -> str:
    email, password = STARTING_ACCOUNTS[role]
    response = client.post(
        "/api/auth/login", json={"email": email, "password": password}
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def ready_to_work(client: TestClient, role: str) -> dict[str, str]:
    """Auth headers of a starting account that has already chosen its own password."""
    token = login(client, role)
    _, password = STARTING_ACCOUNTS[role]
    response = client.post(
        "/api/auth/change-password",
        json={"current_password": password, "new_password": f"{password}-changed"},
        headers=auth(token),
    )
    assert response.status_code == 204, response.text
    return auth(token)


# Helpers shared by the Project and Member tests.

NEW_STUDENT = {
    "role": "student",
    "last_name": "Peeters",
    "programme": "Electronics-ICT",
    "year": "2",
}


def teacher_id(client: TestClient, headers: dict[str, str]) -> int:
    teachers = client.get("/api/teachers", headers=headers).json()
    return next(t["id"] for t in teachers if t["name"] == "Teacher Account")


def create_project(
    client: TestClient, headers: dict[str, str], title: str, minimum=1, maximum=3
) -> int:
    response = client.post(
        "/api/projects",
        json={
            "title": title,
            "product_owner_id": teacher_id(client, headers),
            "team_size_min": minimum,
            "team_size_max": maximum,
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def create_student(client: TestClient, headers: dict[str, str], first_name: str) -> int:
    body = NEW_STUDENT | {
        "first_name": first_name,
        "email": f"{first_name.lower()}@student.vives.be",
    }
    response = client.post("/api/users", json=body, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def add_member(
    client: TestClient,
    headers: dict[str, str],
    project_id: int,
    student_id: int,
    confirm_move: bool = False,
):
    return client.post(
        f"/api/projects/{project_id}/members",
        json={"student_id": student_id, "confirm_move": confirm_move},
        headers=headers,
    )
