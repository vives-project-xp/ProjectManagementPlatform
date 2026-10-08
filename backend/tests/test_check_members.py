import pytest
from fastapi.testclient import TestClient

from pmp_backend.testing import FakeGitHub
from tests.conftest import add_member, create_project, create_student, ready_to_work


def set_username(client: TestClient, staff, user_id: int, login: str | None):
    response = client.put(
        f"/api/users/{user_id}/github-username",
        json={"github_username": login},
        headers=staff,
    )
    assert response.status_code == 200, response.text


def check(client: TestClient, staff, project_id: int):
    return client.post(f"/api/projects/{project_id}/github/check", headers=staff)


def status(client: TestClient, staff, project_id: int) -> dict[str, str]:
    body = client.get(f"/api/projects/{project_id}/github", headers=staff).json()
    return {person["name"]: person["status"] for person in body["people"]}


@pytest.fixture
def drone(client: TestClient, github: FakeGitHub):
    """Drone: Product Owner Teacher Account (Teach-Er), Members Lisa (Lisa-P) and
    Bram (no username); its repository was just created."""
    for login in ("Teach-Er", "Lisa-P", "Ann-X", "Coach-X", "Lisa-New"):
        github.add_account(login)
    staff = ready_to_work(client, "superuser")
    teachers = client.get("/api/users?role=teacher", headers=staff).json()
    set_username(client, staff, teachers[0]["id"], "Teach-Er")
    project = create_project(client, staff, "Drone")
    lisa = create_student(client, staff, "Lisa")
    set_username(client, staff, lisa, "Lisa-P")
    add_member(client, staff, project, lisa)
    add_member(client, staff, project, create_student(client, staff, "Bram"))
    created = client.post("/api/github/repos", headers=staff)
    assert created.json()[0]["created"] is True, created.text
    return staff, project, lisa


def test_creating_invites_members_and_the_product_owner(
    client: TestClient, github: FakeGitHub, drone
):
    staff, project, _ = drone

    repo = github.repos["drone"]

    assert {login: inv.permission for login, inv in repo.invitations.items()} == {
        "lisa-p": "write",
        "teach-er": "admin",
    }
    assert status(client, staff, project) == {
        "Teacher Account": "invited",
        "Bram Peeters": "no_username",
        "Lisa Peeters": "invited",
    }


def test_status_shows_who_has_access(client: TestClient, github: FakeGitHub, drone):
    staff, project, _ = drone

    github.accept("Drone", "Lisa-P")

    body = client.get(f"/api/projects/{project}/github", headers=staff).json()
    assert body["repo_url"] == "https://github.com/TestOrg/Drone"
    lisa = next(p for p in body["people"] if p["name"] == "Lisa Peeters")
    assert lisa == {
        "name": "Lisa Peeters",
        "role": "Member",
        "github_username": "Lisa-P",
        "status": "has_access",
    }


def test_check_invites_a_late_joiner(client: TestClient, github: FakeGitHub, drone):
    staff, project, _ = drone
    ann = create_student(client, staff, "Ann")
    set_username(client, staff, ann, "Ann-X")
    add_member(client, staff, project, ann)

    response = check(client, staff, project)

    assert response.status_code == 200, response.text
    assert response.json()["invited"] == ["Ann-X"]
    assert response.json()["message"] == "Invited Ann-X."
    assert github.repos["drone"].invitations["ann-x"].permission == "write"


def test_check_reinvites_an_expired_invitation(
    client: TestClient, github: FakeGitHub, drone
):
    staff, project, _ = drone
    github.expire("Drone", "Lisa-P")

    response = check(client, staff, project)

    assert response.json()["invited"] == ["Lisa-P"]
    assert github.repos["drone"].invitations["lisa-p"].expired is False


def test_check_fixes_a_wrong_permission(client: TestClient, github: FakeGitHub, drone):
    staff, project, _ = drone
    github.accept("Drone", "Lisa-P")
    github.repos["drone"].collaborators["lisa-p"] = ("Lisa-P", "admin")

    response = check(client, staff, project)

    assert response.json()["updated"] == ["Lisa-P"]
    assert github.repos["drone"].collaborators["lisa-p"] == ("Lisa-P", "write")


def test_check_removes_platform_users_who_left(
    client: TestClient, github: FakeGitHub, drone
):
    staff, project, lisa = drone
    github.accept("Drone", "Lisa-P")
    robot = create_project(client, staff, "Robot")
    add_member(client, staff, robot, lisa, confirm_move=True)

    response = check(client, staff, project)

    assert response.json()["removed"] == ["Lisa-P"]
    assert "lisa-p" not in github.repos["drone"].collaborators


def test_check_removes_deactivated_members(
    client: TestClient, github: FakeGitHub, drone
):
    staff, project, lisa = drone
    client.post(f"/api/users/{lisa}/deactivate", headers=staff)

    response = check(client, staff, project)

    # Only an invitation so far: that is withdrawn.
    assert response.json()["removed"] == ["Lisa-P"]
    assert "lisa-p" not in github.repos["drone"].invitations


def test_a_changed_username_swaps_access(client: TestClient, github: FakeGitHub, drone):
    staff, project, lisa = drone
    github.accept("Drone", "Lisa-P")
    set_username(client, staff, lisa, "Lisa-New")

    response = check(client, staff, project)

    assert response.json()["invited"] == ["Lisa-New"]
    # The platform invited Lisa-P itself, so it removes it (spec #49, Q19).
    assert response.json()["removed"] == ["Lisa-P"]
    assert "lisa-p" not in github.repos["drone"].collaborators


def test_accounts_the_platform_does_not_know_are_never_touched(
    client: TestClient, github: FakeGitHub, drone
):
    staff, project, _ = drone
    github.repos["drone"].collaborators["coach-x"] = ("Coach-X", "admin")

    response = check(client, staff, project)

    assert response.json()["removed"] == []
    assert github.repos["drone"].collaborators["coach-x"] == ("Coach-X", "admin")


def test_nothing_to_do_says_so(client: TestClient, drone):
    staff, project, _ = drone

    response = check(client, staff, project)

    assert response.json()["message"] == "Everything was already in order."


def test_a_deleted_repository_is_reported_and_forgotten(
    client: TestClient, github: FakeGitHub, drone
):
    staff, project, _ = drone
    del github.repos["drone"]

    response = check(client, staff, project)

    assert response.status_code == 200
    assert response.json()["repo_gone"] is True
    assert response.json()["message"] == "The repository no longer exists on GitHub."
    details = client.get(f"/api/projects/{project}", headers=staff).json()
    assert details["repo_url"] is None
    again = client.post("/api/github/repos", headers=staff).json()
    assert [r["title"] for r in again] == ["Drone"]


def test_check_all_checks_every_repository(
    client: TestClient, github: FakeGitHub, drone
):
    staff, project, _ = drone
    ann = create_student(client, staff, "Ann")
    set_username(client, staff, ann, "Ann-X")
    add_member(client, staff, project, ann)

    response = client.post("/api/github/check-all", headers=staff)

    assert response.status_code == 200, response.text
    assert response.json() == [
        {"project_id": project, "title": "Drone", "message": "Invited Ann-X."}
    ]


def test_a_project_without_repository_cannot_be_checked(client: TestClient):
    staff = ready_to_work(client, "teacher")
    project = create_project(client, staff, "Drone")

    response = check(client, staff, project)

    assert response.status_code == 409
    assert response.json()["detail"] == "Drone has no repository yet."


def test_students_cannot_check_or_see_the_status(client: TestClient, drone):
    _, project, _ = drone
    student = ready_to_work(client, "student")

    assert check(client, student, project).status_code == 403
    assert (
        client.get(f"/api/projects/{project}/github", headers=student).status_code
        == 403
    )
    assert client.post("/api/github/check-all", headers=student).status_code == 403
