import pytest
from fastapi.testclient import TestClient

from pmp_backend.testing import OWNER_ID, FakeMember, FakeTrello
from tests.conftest import add_member, create_project, create_student, ready_to_work

TEACHER_EMAIL = "teacher@pmp.local"


def check(client: TestClient, staff, project_id: int):
    return client.post(f"/api/projects/{project_id}/trello/check", headers=staff)


def status(client: TestClient, staff, project_id: int) -> dict[str, str]:
    body = client.get(f"/api/projects/{project_id}/trello", headers=staff).json()
    return {person["name"]: person["status"] for person in body["people"]}


@pytest.fixture
def drone(client: TestClient, trello: FakeTrello):
    """Drone: Product Owner Teacher Account, Members Lisa (has a Trello account)
    and Bram (none yet); its board was just created."""
    trello.accounts.add("lisa@student.vives.be")
    staff = ready_to_work(client, "superuser")
    project = create_project(client, staff, "Drone")
    lisa = create_student(client, staff, "Lisa")
    add_member(client, staff, project, lisa)
    add_member(client, staff, project, create_student(client, staff, "Bram"))
    created = client.post("/api/trello/boards", headers=staff)
    assert created.json()[0]["created"] is True, created.text
    return staff, project, lisa


def test_status_shows_who_has_access_and_who_still_signs_up(
    client: TestClient, trello: FakeTrello, drone
):
    staff, project, _ = drone

    body = client.get(f"/api/projects/{project}/trello", headers=staff).json()

    assert body["board_url"] == trello.board_named("Drone").url
    assert body["people"] == [
        {
            "name": "Teacher Account",
            "role": "Product Owner",
            "email": TEACHER_EMAIL,
            "status": "invited",
        },
        {
            "name": "Bram Peeters",
            "role": "Member",
            "email": "bram@student.vives.be",
            "status": "invited",
        },
        {
            "name": "Lisa Peeters",
            "role": "Member",
            "email": "lisa@student.vives.be",
            "status": "has_access",
        },
    ]

    trello.sign_up("bram@student.vives.be")

    assert status(client, staff, project)["Bram Peeters"] == "has_access"


def test_check_invites_a_late_joiner(client: TestClient, trello: FakeTrello, drone):
    staff, project, _ = drone
    add_member(client, staff, project, create_student(client, staff, "Ann"))
    assert status(client, staff, project)["Ann Peeters"] == "not_invited"

    response = check(client, staff, project)

    assert response.status_code == 200, response.text
    assert response.json()["message"] == "Invited Ann Peeters."
    assert trello.board_named("Drone").emails()["ann@student.vives.be"] == "normal"
    assert status(client, staff, project)["Ann Peeters"] == "invited"


def test_check_removes_members_who_left(client: TestClient, trello: FakeTrello, drone):
    staff, project, lisa = drone
    robot = create_project(client, staff, "Robot")
    add_member(client, staff, robot, lisa, confirm_move=True)

    response = check(client, staff, project)

    assert response.json()["message"] == "Removed Lisa Peeters."
    assert "lisa@student.vives.be" not in trello.board_named("Drone").emails()


def test_check_removes_deactivated_members(
    client: TestClient, trello: FakeTrello, drone
):
    staff, project, lisa = drone
    client.post(f"/api/users/{lisa}/deactivate", headers=staff)

    check(client, staff, project)

    assert "lisa@student.vives.be" not in trello.board_named("Drone").emails()


def test_a_changed_email_swaps_the_member(
    client: TestClient, trello: FakeTrello, drone
):
    staff, project, lisa = drone
    edited = client.put(
        f"/api/users/{lisa}",
        json={
            "first_name": "Lisa",
            "last_name": "Peeters",
            "email": "lisa.peeters@student.vives.be",
            "programme": "Electronics-ICT",
            "year": "2",
        },
        headers=staff,
    )
    assert edited.status_code == 200, edited.text

    response = check(client, staff, project)

    assert response.json()["message"] == "Invited Lisa Peeters. Removed Lisa Peeters."
    emails = trello.board_named("Drone").emails()
    assert "lisa@student.vives.be" not in emails
    assert emails["lisa.peeters@student.vives.be"] == "normal"


def test_check_fixes_a_changed_role(client: TestClient, trello: FakeTrello, drone):
    staff, project, _ = drone
    board = trello.board_named("Drone")
    lisa = next(m for m in board.members.values() if m.email == "lisa@student.vives.be")
    lisa.member_type = "admin"

    response = check(client, staff, project)

    assert response.json()["message"] == "Changed the role of Lisa Peeters."
    assert lisa.member_type == "normal"


def test_members_the_platform_did_not_add_are_never_touched(
    client: TestClient, trello: FakeTrello, drone
):
    staff, project, _ = drone
    board = trello.board_named("Drone")
    board.members["coach"] = FakeMember("coach", "coach@vives.be", "normal")

    response = check(client, staff, project)

    assert response.json()["message"] == "Everything was already in order."
    assert {"coach", OWNER_ID} <= set(board.members)


def test_someone_removed_by_hand_is_invited_again(
    client: TestClient, trello: FakeTrello, drone
):
    staff, project, _ = drone
    board = trello.board_named("Drone")
    lisa = next(
        k for k, m in board.members.items() if m.email == "lisa@student.vives.be"
    )
    del board.members[lisa]

    response = check(client, staff, project)

    assert response.json()["message"] == "Invited Lisa Peeters."
    assert "lisa@student.vives.be" in board.emails()


def test_check_renames_the_board_after_the_title(
    client: TestClient, trello: FakeTrello, drone
):
    staff, project, _ = drone
    board = trello.board_named("Drone")
    board.name = "Old name"
    trello.workspaces[board.workspace_id] = "Old name"

    response = check(client, staff, project)

    assert response.json()["message"] == "Renamed the board."
    assert board.name == "Drone"
    assert trello.workspaces[board.workspace_id] == "Drone"


def test_a_deleted_board_is_reported_and_forgotten(
    client: TestClient, trello: FakeTrello, drone
):
    staff, project, _ = drone
    del trello.boards[trello.board_named("Drone").id]

    shown = client.get(f"/api/projects/{project}/trello", headers=staff)
    response = check(client, staff, project)

    assert shown.status_code == 409
    assert shown.json()["detail"] == (
        "The Trello board no longer exists. Check members to forget it."
    )
    assert response.json()["board_gone"] is True
    assert response.json()["message"] == "The Trello board no longer exists."
    details = client.get(f"/api/projects/{project}", headers=staff).json()
    assert details["trello_board_url"] is None
    # The next "Create Trello boards for all Projects" makes a new one.
    again = client.post("/api/trello/boards", headers=staff).json()
    assert [r["title"] for r in again] == ["Drone"]


def test_check_all_checks_every_board(client: TestClient, trello: FakeTrello, drone):
    staff, project, _ = drone
    add_member(client, staff, project, create_student(client, staff, "Ann"))

    response = client.post("/api/trello/check-all", headers=staff)

    assert response.json() == [
        {"project_id": project, "title": "Drone", "message": "Invited Ann Peeters."}
    ]


def test_trello_down_is_reported(client: TestClient, trello: FakeTrello, drone):
    staff, project, _ = drone
    trello.failing = True

    response = check(client, staff, project)
    all_checked = client.post("/api/trello/check-all", headers=staff)

    assert response.status_code == 503
    assert all_checked.json()[0]["message"] == (
        "Failed. Trello can't be reached. Try again later."
    )


def test_a_project_without_board_cannot_be_checked(client: TestClient):
    staff = ready_to_work(client, "teacher")
    project = create_project(client, staff, "Drone")

    response = check(client, staff, project)

    assert response.status_code == 409
    assert response.json()["detail"] == "Drone has no Trello board yet."


# Students


def test_a_student_sees_their_board_and_next_step(
    client: TestClient, trello: FakeTrello
):
    staff = ready_to_work(client, "superuser")
    project = create_project(client, staff, "Drone")
    students = client.get("/api/users?role=student", headers=staff).json()
    add_member(client, staff, project, students[0]["id"])
    client.post("/api/trello/boards", headers=staff)
    student = ready_to_work(client, "student")

    invited = client.get("/api/my-project/trello", headers=student).json()
    trello.sign_up("student@pmp.local")
    joined = client.get("/api/my-project/trello", headers=student).json()

    board_url = trello.board_named("Drone").url
    assert invited == {
        "board_url": board_url,
        "status": "invited",
        "email": "student@pmp.local",
    }
    assert joined["status"] == "has_access"


def test_a_student_without_board_sees_none(client: TestClient):
    student = ready_to_work(client, "student")

    response = client.get("/api/my-project/trello", headers=student)

    assert response.json() == {
        "board_url": None,
        "status": "no_board",
        "email": "student@pmp.local",
    }


def test_students_cannot_check_or_see_the_status(client: TestClient, drone):
    _, project, _ = drone
    student = ready_to_work(client, "student")

    assert check(client, student, project).status_code == 403
    assert client.post("/api/trello/check-all", headers=student).status_code == 403
    response = client.get(f"/api/projects/{project}/trello", headers=student)
    assert response.status_code == 403
