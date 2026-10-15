from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from pmp_backend.app import create_app
from pmp_backend.settings import Settings
from pmp_backend.testing import FakeTrello
from tests.conftest import (
    add_member,
    create_project,
    create_student,
    ready_to_work,
)

TEACHER_EMAIL = "teacher@pmp.local"


def details(client: TestClient, headers, project_id: int) -> dict:
    return client.get(f"/api/projects/{project_id}", headers=headers).json()


def create_boards(client: TestClient, headers):
    return client.post("/api/trello/boards", headers=headers)


def project_with_member(client: TestClient, headers, title: str, student: str) -> int:
    project = create_project(client, headers, title)
    add_member(client, headers, project, create_student(client, headers, student))
    return project


def test_create_for_all_makes_a_workspace_and_board_per_project_with_members(
    client: TestClient, trello: FakeTrello
):
    headers = ready_to_work(client, "superuser")
    drone = project_with_member(client, headers, "Drone", "Lisa")
    greenhouse = project_with_member(client, headers, "Smart Greenhouse", "Bram")
    empty = create_project(client, headers, "Nobody yet")
    archived = project_with_member(client, headers, "Old one", "Ann")
    client.post(f"/api/projects/{archived}/archive", headers=headers)

    response = create_boards(client, headers)

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
    assert sorted(trello.workspaces.values()) == ["Drone", "Smart Greenhouse"]
    board = trello.board_named("Drone")
    assert trello.workspaces[board.workspace_id] == "Drone"
    assert board.private
    assert board.lists == ["Backlog", "To do", "Doing", "Review", "Done"]
    assert details(client, headers, drone)["trello_board_url"] == board.url
    assert details(client, headers, empty)["trello_board_url"] is None


def test_members_and_the_product_owner_are_invited_by_email(
    client: TestClient, trello: FakeTrello
):
    trello.accounts.add("lisa@student.vives.be")
    headers = ready_to_work(client, "superuser")
    drone = project_with_member(client, headers, "Drone", "Lisa")
    add_member(client, headers, drone, create_student(client, headers, "Bram"))

    create_boards(client, headers)

    board = trello.board_named("Drone")
    assert board.emails() == {
        "lisa@student.vives.be": "normal",
        "bram@student.vives.be": "normal",
        TEACHER_EMAIL: "admin",
    }
    unconfirmed = {m.email for m in board.members.values() if m.unconfirmed}
    # Lisa has a Trello account and joins at once; the others still sign up.
    assert unconfirmed == {"bram@student.vives.be", TEACHER_EMAIL}


def test_deactivated_members_are_not_invited(client: TestClient, trello: FakeTrello):
    headers = ready_to_work(client, "superuser")
    drone = project_with_member(client, headers, "Drone", "Lisa")
    bram = create_student(client, headers, "Bram")
    add_member(client, headers, drone, bram)
    client.post(f"/api/users/{bram}/deactivate", headers=headers)

    create_boards(client, headers)

    assert "bram@student.vives.be" not in trello.board_named("Drone").emails()


def test_a_second_run_creates_only_new_ones(client: TestClient, trello: FakeTrello):
    headers = ready_to_work(client, "superuser")
    project_with_member(client, headers, "Drone", "Lisa")
    create_boards(client, headers)
    project_with_member(client, headers, "Robot", "Bram")

    response = create_boards(client, headers)

    assert [r["title"] for r in response.json()] == ["Robot"]
    assert sorted(trello.workspaces.values()) == ["Drone", "Robot"]


def test_one_failure_does_not_stop_the_others(client: TestClient, trello: FakeTrello):
    trello.refused_names.add("Drone")
    headers = ready_to_work(client, "superuser")
    drone = project_with_member(client, headers, "Drone", "Lisa")
    project_with_member(client, headers, "Robot", "Bram")

    results = create_boards(client, headers).json()

    assert results[0] == {
        "project_id": drone,
        "title": "Drone",
        "created": False,
        "message": "Trello refused: the board limit was reached",
    }
    assert results[1]["created"] is True
    assert details(client, headers, drone)["trello_board_url"] is None
    # The half-made Workspace is gone again, so a retry starts clean.
    assert sorted(trello.workspaces.values()) == ["Robot"]


def test_trello_down_is_reported_per_project(client: TestClient, trello: FakeTrello):
    headers = ready_to_work(client, "superuser")
    drone = project_with_member(client, headers, "Drone", "Lisa")
    trello.failing = True

    results = create_boards(client, headers).json()

    assert results == [
        {
            "project_id": drone,
            "title": "Drone",
            "created": False,
            "message": "Trello can't be reached. Try again later.",
        }
    ]


def test_trello_status_says_it_is_connected(client: TestClient):
    headers = ready_to_work(client, "teacher")

    response = client.get("/api/trello/status", headers=headers)

    assert response.json() == {"connected": True}


@pytest.fixture
def unconnected_client(settings: Settings, trello: FakeTrello) -> Iterator[TestClient]:
    app = create_app(settings.model_copy(update={"trello_token": None}))
    app.state.trello = trello
    with TestClient(app) as client:
        yield client


def test_without_a_token_trello_is_not_connected(unconnected_client: TestClient):
    headers = ready_to_work(unconnected_client, "teacher")

    status = unconnected_client.get("/api/trello/status", headers=headers)
    response = create_boards(unconnected_client, headers)

    assert status.json() == {"connected": False}
    assert response.status_code == 409
    assert response.json()["detail"] == "Trello isn't connected."


def test_students_cannot_create_boards(client: TestClient):
    student = ready_to_work(client, "student")

    assert create_boards(client, student).status_code == 403
    assert client.get("/api/trello/status", headers=student).status_code == 403
