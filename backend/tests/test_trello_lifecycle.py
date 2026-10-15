import pytest
from fastapi.testclient import TestClient

from pmp_backend.testing import FakeTrello
from tests.conftest import add_member, create_project, create_student, ready_to_work


@pytest.fixture
def drone(client: TestClient):
    """Drone, with a Member and its Trello board."""
    staff = ready_to_work(client, "superuser")
    project = create_project(client, staff, "Drone")
    add_member(client, staff, project, create_student(client, staff, "Lisa"))
    created = client.post("/api/trello/boards", headers=staff)
    assert created.json()[0]["created"] is True, created.text
    return staff, project


def rename(client: TestClient, staff, project_id: int, title: str):
    current = client.get(f"/api/projects/{project_id}", headers=staff).json()
    return client.put(
        f"/api/projects/{project_id}",
        json={
            "title": title,
            "description": current["description"],
            "product_owner_id": current["product_owner"]["id"],
            "team_size_min": current["team_size_min"],
            "team_size_max": current["team_size_max"],
        },
        headers=staff,
    )


def test_archiving_closes_and_restoring_reopens_the_board(
    client: TestClient, trello: FakeTrello, drone
):
    staff, project = drone
    board = trello.board_named("Drone")

    archived = client.post(f"/api/projects/{project}/archive", headers=staff)
    closed = board.closed
    restored = client.post(f"/api/projects/{project}/restore", headers=staff)

    assert archived.status_code == 200, archived.text
    assert archived.json()["warning"] is None
    assert closed is True
    assert restored.json()["warning"] is None
    assert board.closed is False


def test_archiving_still_works_when_trello_is_down(
    client: TestClient, trello: FakeTrello, drone
):
    staff, project = drone
    trello.failing = True

    response = client.post(f"/api/projects/{project}/archive", headers=staff)

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "archived"
    assert response.json()["warning"] == (
        "Drone was archived, but its Trello board could not be closed: "
        "Trello can't be reached. Try again later."
    )


def test_renaming_the_project_renames_the_board(
    client: TestClient, trello: FakeTrello, drone
):
    staff, project = drone
    board = trello.board_named("Drone")

    response = rename(client, staff, project, "Flying Drone")

    assert response.status_code == 200, response.text
    assert response.json()["warning"] is None
    assert board.name == "Flying Drone"
    assert trello.workspaces[board.workspace_id] == "Flying Drone"


def test_renaming_still_saves_when_trello_is_down(
    client: TestClient, trello: FakeTrello, drone
):
    staff, project = drone
    board = trello.board_named("Drone")
    trello.failing = True

    response = rename(client, staff, project, "Flying Drone")

    assert response.status_code == 200, response.text
    assert response.json()["title"] == "Flying Drone"
    assert response.json()["warning"] == (
        "Saved, but the Trello board couldn't be renamed: Trello can't be reached. "
        "Try again later. Check members renames it later."
    )
    # Check members catches the name up once Trello is back.
    trello.failing = False
    checked = client.post(f"/api/projects/{project}/trello/check", headers=staff)
    assert checked.json()["renamed"] is True
    assert board.name == "Flying Drone"


def test_other_changes_leave_trello_alone(
    client: TestClient, trello: FakeTrello, drone
):
    staff, project = drone
    trello.failing = True

    response = rename(client, staff, project, "Drone")

    assert response.json()["warning"] is None


def test_a_project_with_a_board_cannot_be_deleted(client: TestClient, drone):
    staff, project = drone
    student = client.get(f"/api/projects/{project}", headers=staff).json()["members"]
    client.delete(f"/api/projects/{project}/members/{student[0]['id']}", headers=staff)

    response = client.delete(f"/api/projects/{project}", headers=staff)

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "This Project has a Trello board; archive it instead."
    )
