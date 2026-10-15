import pytest
from fastapi.testclient import TestClient

from pmp_backend.testing import FakeGitHub
from tests.conftest import add_member, create_project, ready_to_work


def set_username(client: TestClient, staff, user_id: int, login: str) -> None:
    response = client.put(
        f"/api/users/{user_id}/github-username",
        json={"github_username": login},
        headers=staff,
    )
    assert response.status_code == 200, response.text


@pytest.fixture
def drone(client: TestClient, github: FakeGitHub):
    """Drone with the starting Student as Member and a repository."""
    github.add_account("Stu-D")
    staff = ready_to_work(client, "superuser")
    student = ready_to_work(client, "student")
    me = client.get("/api/auth/me", headers=student).json()["id"]
    project = create_project(client, staff, "Drone")
    add_member(client, staff, project, me)
    assert client.post("/api/github/repos", headers=staff).json()[0]["created"]
    return staff, student, project, me


def my_github(client: TestClient, student) -> dict:
    response = client.get("/api/my-project/github", headers=student)
    assert response.status_code == 200, response.text
    return response.json()


# The Student's view


def test_a_student_without_username_is_told_to_add_one(client: TestClient, drone):
    _, student, _, _ = drone

    assert my_github(client, student) == {
        "repo_url": "https://github.com/TestOrg/Drone",
        "status": "no_username",
        "invitation_url": None,
    }


def test_an_invited_student_gets_the_invitation_link(
    client: TestClient, github: FakeGitHub, drone
):
    staff, student, project, me = drone
    set_username(client, staff, me, "Stu-D")
    client.post(f"/api/projects/{project}/github/check", headers=staff)

    shown = my_github(client, student)

    assert shown["status"] == "invited"
    assert shown["invitation_url"] == "https://github.com/TestOrg/Drone/invitations"
    github.accept("Drone", "Stu-D")
    assert my_github(client, student)["status"] == "has_access"


def test_not_invited_yet_until_someone_checks(client: TestClient, drone):
    staff, student, _, me = drone
    set_username(client, staff, me, "Stu-D")

    assert my_github(client, student)["status"] == "not_invited"


def test_a_student_without_repository_sees_nothing(client: TestClient):
    staff = ready_to_work(client, "superuser")
    student = ready_to_work(client, "student")
    me = client.get("/api/auth/me", headers=student).json()["id"]
    project = create_project(client, staff, "Drone")
    add_member(client, staff, project, me)

    assert my_github(client, student) == {
        "repo_url": None,
        "status": "no_repository",
        "invitation_url": None,
    }


def test_only_students_have_a_my_project_github(client: TestClient):
    teacher = ready_to_work(client, "teacher")

    assert client.get("/api/my-project/github", headers=teacher).status_code == 403


# Archiving


def test_archiving_archives_the_repository_and_restoring_unarchives_it(
    client: TestClient, github: FakeGitHub, drone
):
    staff, _, project, _ = drone

    archived = client.post(f"/api/projects/{project}/archive", headers=staff)

    assert archived.status_code == 200, archived.text
    assert archived.json()["warning"] is None
    assert github.repos["drone"].archived is True
    restored = client.post(f"/api/projects/{project}/restore", headers=staff)
    assert restored.json()["warning"] is None
    assert github.repos["drone"].archived is False


def test_github_failing_still_archives_with_a_warning(
    client: TestClient, github: FakeGitHub, drone
):
    staff, _, project, _ = drone
    github.failing = True

    response = client.post(f"/api/projects/{project}/archive", headers=staff)

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "archived"
    assert response.json()["warning"] == (
        "Drone was archived, but its repository could not be archived on GitHub: "
        "GitHub can't be reached. Try again later."
    )


def test_a_project_without_repository_archives_without_github(
    client: TestClient, github: FakeGitHub
):
    github.failing = True
    staff = ready_to_work(client, "teacher")
    project = create_project(client, staff, "Drone")

    response = client.post(f"/api/projects/{project}/archive", headers=staff)

    assert response.status_code == 200
    assert response.json()["warning"] is None


# Deleting


def test_a_project_with_a_repository_cannot_be_deleted(client: TestClient, drone):
    staff, _, project, me = drone
    client.delete(f"/api/projects/{project}/members/{me}", headers=staff)

    response = client.delete(f"/api/projects/{project}", headers=staff)

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "This Project has a GitHub repository; archive it instead."
    )
