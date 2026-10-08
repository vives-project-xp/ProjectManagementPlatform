from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from pmp_backend.app import create_app
from pmp_backend.settings import Settings
from pmp_backend.testing import FakeGitHub
from tests.conftest import (
    add_member,
    create_project,
    create_student,
    ready_to_work,
)


def details(client: TestClient, headers, project_id: int) -> dict:
    return client.get(f"/api/projects/{project_id}", headers=headers).json()


def set_name(client: TestClient, headers, project_id: int, name: str | None):
    return client.put(
        f"/api/projects/{project_id}/repo-name",
        json={"repo_name": name},
        headers=headers,
    )


def create_repos(client: TestClient, headers):
    return client.post("/api/github/repos", headers=headers)


def project_with_member(client: TestClient, headers, title: str, student: str) -> int:
    project = create_project(client, headers, title)
    add_member(client, headers, project, create_student(client, headers, student))
    return project


# The repository name


@pytest.mark.parametrize(
    ("title", "suggested"),
    [
        ("Smart Greenhouse", "SmartGreenhouse"),
        ("Tétris arcade-game 2.0", "TetrisArcadeGame20"),
        ("AI drone", "AIDrone"),
    ],
)
def test_the_name_is_suggested_from_the_title(
    client: TestClient, title: str, suggested: str
):
    headers = ready_to_work(client, "teacher")
    project = create_project(client, headers, title)

    shown = details(client, headers, project)

    assert shown["repo_name"] == suggested
    assert shown["repo_url"] is None


def test_teacher_changes_the_name_and_can_go_back(client: TestClient):
    headers = ready_to_work(client, "teacher")
    project = create_project(client, headers, "Smart Greenhouse")

    changed = set_name(client, headers, project, "SmartGreenhouse2026")
    back = set_name(client, headers, project, None)

    assert changed.status_code == 200, changed.text
    assert changed.json()["repo_name"] == "SmartGreenhouse2026"
    assert back.json()["repo_name"] == "SmartGreenhouse"


@pytest.mark.parametrize("name", ["has space", "a/b", "..", "x" * 101, "émoji"])
def test_an_invalid_name_is_refused(client: TestClient, name: str):
    headers = ready_to_work(client, "teacher")
    project = create_project(client, headers, "Smart Greenhouse")

    response = set_name(client, headers, project, name)

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "A repository name can only use letters, digits, '-', '_' and '.' "
        "(at most 100 characters)."
    )


# Creating


def test_create_for_all_makes_public_empty_repos_for_projects_with_members(
    client: TestClient, github: FakeGitHub
):
    headers = ready_to_work(client, "superuser")
    drone = project_with_member(client, headers, "Drone", "Lisa")
    greenhouse = project_with_member(client, headers, "Smart Greenhouse", "Bram")
    empty = create_project(client, headers, "Nobody yet")
    archived = project_with_member(client, headers, "Old one", "Ann")
    client.post(f"/api/projects/{archived}/archive", headers=headers)
    set_name(client, headers, greenhouse, "Greenhouse2026")

    response = create_repos(client, headers)

    assert response.status_code == 200, response.text
    assert response.json() == [
        {"project_id": drone, "title": "Drone", "created": True, "message": "Created"},
        {
            "project_id": greenhouse,
            "title": "Smart Greenhouse",
            "created": True,
            "message": "Created",
        },
    ]
    assert sorted(github.repos) == ["drone", "greenhouse2026"]
    assert all(
        repo.org == "TestOrg" and not repo.private and repo.empty
        for repo in github.repos.values()
    )
    assert details(client, headers, drone)["repo_url"] == (
        "https://github.com/TestOrg/Drone"
    )
    assert details(client, headers, empty)["repo_url"] is None


def test_a_second_run_creates_only_new_ones(client: TestClient, github: FakeGitHub):
    headers = ready_to_work(client, "superuser")
    project_with_member(client, headers, "Drone", "Lisa")
    create_repos(client, headers)
    project_with_member(client, headers, "Robot", "Bram")

    response = create_repos(client, headers)

    assert [r["title"] for r in response.json()] == ["Robot"]
    assert sorted(github.repos) == ["drone", "robot"]


def test_one_failure_does_not_stop_the_others(client: TestClient, github: FakeGitHub):
    github.add_repo("TestOrg", "Drone")
    headers = ready_to_work(client, "superuser")
    drone = project_with_member(client, headers, "Drone", "Lisa")
    project_with_member(client, headers, "Robot", "Bram")

    results = create_repos(client, headers).json()

    assert results[0] == {
        "project_id": drone,
        "title": "Drone",
        "created": False,
        "message": "A repository called Drone already exists in TestOrg. "
        "Choose another Repository name.",
    }
    assert results[1]["created"] is True
    assert details(client, headers, drone)["repo_url"] is None


def test_the_name_is_locked_once_the_repo_exists(client: TestClient):
    headers = ready_to_work(client, "superuser")
    drone = project_with_member(client, headers, "Drone", "Lisa")
    create_repos(client, headers)

    response = set_name(client, headers, drone, "Other")

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Drone already has its repository, so its name can't change."
    )


def test_renaming_the_project_keeps_the_repo_name(client: TestClient):
    headers = ready_to_work(client, "superuser")
    drone = project_with_member(client, headers, "Drone", "Lisa")
    create_repos(client, headers)
    current = details(client, headers, drone)

    client.put(
        f"/api/projects/{drone}",
        json={
            "title": "Flying Drone",
            "product_owner_id": current["product_owner"]["id"],
            "team_size_min": 1,
            "team_size_max": 3,
        },
        headers=headers,
    )

    assert details(client, headers, drone)["repo_name"] == "Drone"


def test_github_status_says_whether_it_is_connected(client: TestClient):
    headers = ready_to_work(client, "teacher")

    response = client.get("/api/github/status", headers=headers)

    assert response.json() == {"connected": True, "org": "TestOrg"}


@pytest.fixture
def unconnected_client(settings: Settings, github: FakeGitHub) -> Iterator[TestClient]:
    app = create_app(settings.model_copy(update={"github_token": None}))
    app.state.github = github
    with TestClient(app) as client:
        yield client


def test_without_a_token_github_is_not_connected(unconnected_client: TestClient):
    headers = ready_to_work(unconnected_client, "teacher")

    status = unconnected_client.get("/api/github/status", headers=headers)
    response = create_repos(unconnected_client, headers)

    assert status.json() == {"connected": False, "org": "TestOrg"}
    assert response.status_code == 409
    assert response.json()["detail"] == "GitHub isn't connected."


def test_students_cannot_create_or_rename(client: TestClient):
    teacher = ready_to_work(client, "teacher")
    project = create_project(client, teacher, "Drone")
    student = ready_to_work(client, "student")

    assert create_repos(client, student).status_code == 403
    assert set_name(client, student, project, "X").status_code == 403
    assert client.get("/api/github/status", headers=student).status_code == 403
