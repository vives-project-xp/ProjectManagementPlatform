from fastapi.testclient import TestClient

from tests.conftest import (
    add_member,
    create_project,
    create_student,
    ready_to_work,
    teacher_id,
)


def member_names(client, headers, project_id) -> list[str]:
    details = client.get(f"/api/projects/{project_id}", headers=headers).json()
    return [member["name"] for member in details["members"]]


def test_teacher_adds_a_student_as_member(client: TestClient):
    superuser = ready_to_work(client, "superuser")
    lisa = create_student(client, superuser, "Lisa")
    teacher = ready_to_work(client, "teacher")
    project = create_project(client, teacher, "Smart Greenhouse")

    response = add_member(client, teacher, project, lisa)

    assert response.status_code == 200, response.text
    assert member_names(client, teacher, project) == ["Lisa Peeters"]
    listed = client.get("/api/projects", headers=teacher).json()
    assert listed[0]["member_count"] == 1


def test_only_students_can_be_members(client: TestClient):
    superuser = ready_to_work(client, "superuser")
    project = create_project(client, superuser, "Smart Greenhouse")
    me = client.get("/api/auth/me", headers=superuser).json()["id"]

    response = add_member(client, superuser, project, me)

    assert response.status_code == 422
    assert response.json()["detail"] == "Only Students can be Members."


def test_deactivated_student_cannot_be_added(client: TestClient):
    superuser = ready_to_work(client, "superuser")
    lisa = create_student(client, superuser, "Lisa")
    client.post(f"/api/users/{lisa}/deactivate", headers=superuser)
    project = create_project(client, superuser, "Smart Greenhouse")

    response = add_member(client, superuser, project, lisa)

    assert response.status_code == 422
    assert "is deactivated" in response.json()["detail"]


def test_full_project_refuses_another_member(client: TestClient):
    superuser = ready_to_work(client, "superuser")
    project = create_project(client, superuser, "Drone", minimum=1, maximum=1)
    add_member(client, superuser, project, create_student(client, superuser, "Lisa"))

    response = add_member(
        client, superuser, project, create_student(client, superuser, "Tom")
    )

    assert response.status_code == 409
    assert "Drone is full" in response.json()["detail"]


def test_adding_twice_is_refused(client: TestClient):
    superuser = ready_to_work(client, "superuser")
    project = create_project(client, superuser, "Drone")
    lisa = create_student(client, superuser, "Lisa")
    add_member(client, superuser, project, lisa)

    response = add_member(client, superuser, project, lisa)

    assert response.status_code == 409
    assert "already a Member of Drone" in response.json()["detail"]


def test_moving_needs_confirmation_and_then_happens_in_one_step(client: TestClient):
    superuser = ready_to_work(client, "superuser")
    drone = create_project(client, superuser, "Drone")
    greenhouse = create_project(client, superuser, "Smart Greenhouse")
    lisa = create_student(client, superuser, "Lisa")
    add_member(client, superuser, drone, lisa)

    unconfirmed = add_member(client, superuser, greenhouse, lisa)

    assert unconfirmed.status_code == 409
    body = unconfirmed.json()
    assert body["code"] == "move_confirmation_needed"
    assert body["detail"] == (
        "Lisa Peeters is a Member of Drone. Move Lisa Peeters to Smart Greenhouse?"
    )
    assert member_names(client, superuser, drone) == ["Lisa Peeters"]

    confirmed = add_member(client, superuser, greenhouse, lisa, confirm_move=True)

    assert confirmed.status_code == 200, confirmed.text
    assert member_names(client, superuser, drone) == []
    assert member_names(client, superuser, greenhouse) == ["Lisa Peeters"]


def test_move_into_a_full_project_is_refused(client: TestClient):
    superuser = ready_to_work(client, "superuser")
    drone = create_project(client, superuser, "Drone")
    full = create_project(client, superuser, "Greenhouse", minimum=1, maximum=1)
    lisa = create_student(client, superuser, "Lisa")
    add_member(client, superuser, drone, lisa)
    add_member(client, superuser, full, create_student(client, superuser, "Tom"))

    response = add_member(client, superuser, full, lisa, confirm_move=True)

    assert response.status_code == 409
    assert member_names(client, superuser, drone) == ["Lisa Peeters"]


def test_teacher_removes_a_member(client: TestClient):
    superuser = ready_to_work(client, "superuser")
    project = create_project(client, superuser, "Drone")
    lisa = create_student(client, superuser, "Lisa")
    add_member(client, superuser, project, lisa)

    response = client.delete(
        f"/api/projects/{project}/members/{lisa}", headers=superuser
    )

    assert response.status_code == 200, response.text
    assert member_names(client, superuser, project) == []


def test_removing_a_non_member_is_not_found(client: TestClient):
    superuser = ready_to_work(client, "superuser")
    project = create_project(client, superuser, "Drone")
    lisa = create_student(client, superuser, "Lisa")

    response = client.delete(
        f"/api/projects/{project}/members/{lisa}", headers=superuser
    )

    assert response.status_code == 404


def test_deactivated_members_stay_and_count_towards_team_size(client: TestClient):
    superuser = ready_to_work(client, "superuser")
    project = create_project(client, superuser, "Drone", minimum=1, maximum=1)
    lisa = create_student(client, superuser, "Lisa")
    add_member(client, superuser, project, lisa)
    client.post(f"/api/users/{lisa}/deactivate", headers=superuser)

    details = client.get(f"/api/projects/{project}", headers=superuser).json()
    another = add_member(
        client, superuser, project, create_student(client, superuser, "Tom")
    )

    assert details["members"][0]["is_active"] is False
    assert details["member_count"] == 1
    assert another.status_code == 409


def test_lowering_the_maximum_below_the_members_is_refused(client: TestClient):
    superuser = ready_to_work(client, "superuser")
    project = create_project(client, superuser, "Drone", minimum=1, maximum=3)
    for name in ("Lisa", "Tom"):
        add_member(client, superuser, project, create_student(client, superuser, name))

    response = client.put(
        f"/api/projects/{project}",
        json={
            "title": "Drone",
            "product_owner_id": teacher_id(client, superuser),
            "team_size_min": 1,
            "team_size_max": 1,
        },
        headers=superuser,
    )

    assert response.status_code == 409
    assert "2 Members" in response.json()["detail"]


def test_students_list_shows_their_project(client: TestClient):
    superuser = ready_to_work(client, "superuser")
    project = create_project(client, superuser, "Drone")
    lisa = create_student(client, superuser, "Lisa")
    add_member(client, superuser, project, lisa)

    students = client.get("/api/students", headers=superuser).json()

    by_name = {student["name"]: student for student in students}
    assert by_name["Lisa Peeters"]["project"] == {"id": project, "title": "Drone"}
    assert by_name["Student Account"]["project"] is None


def test_students_cannot_manage_members(client: TestClient):
    superuser = ready_to_work(client, "superuser")
    project = create_project(client, superuser, "Drone")
    student = ready_to_work(client, "student")
    me = client.get("/api/auth/me", headers=student).json()["id"]

    assert add_member(client, student, project, me).status_code == 403
    assert (
        client.delete(f"/api/projects/{project}/members/{me}", headers=student)
    ).status_code == 403
    assert client.get("/api/students", headers=student).status_code == 403
