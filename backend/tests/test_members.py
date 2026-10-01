from fastapi.testclient import TestClient

from tests.conftest import ready_to_work

NEW_STUDENT = {
    "role": "student",
    "last_name": "Peeters",
    "temporary_password": "welcome-student",
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


def add(client, headers, project_id, student_id, confirm_move=False):
    return client.post(
        f"/api/projects/{project_id}/members",
        json={"student_id": student_id, "confirm_move": confirm_move},
        headers=headers,
    )


def member_names(client, headers, project_id) -> list[str]:
    details = client.get(f"/api/projects/{project_id}", headers=headers).json()
    return [member["name"] for member in details["members"]]


def test_teacher_adds_a_student_as_member(client: TestClient):
    superuser = ready_to_work(client, "superuser")
    lisa = create_student(client, superuser, "Lisa")
    teacher = ready_to_work(client, "teacher")
    project = create_project(client, teacher, "Smart Greenhouse")

    response = add(client, teacher, project, lisa)

    assert response.status_code == 200, response.text
    assert member_names(client, teacher, project) == ["Lisa Peeters"]
    listed = client.get("/api/projects", headers=teacher).json()
    assert listed[0]["member_count"] == 1


def test_only_students_can_be_members(client: TestClient):
    superuser = ready_to_work(client, "superuser")
    project = create_project(client, superuser, "Smart Greenhouse")
    me = client.get("/api/auth/me", headers=superuser).json()["id"]

    response = add(client, superuser, project, me)

    assert response.status_code == 422
    assert response.json()["detail"] == "Only Students can be Members."


def test_deactivated_student_cannot_be_added(client: TestClient):
    superuser = ready_to_work(client, "superuser")
    lisa = create_student(client, superuser, "Lisa")
    client.post(f"/api/users/{lisa}/deactivate", headers=superuser)
    project = create_project(client, superuser, "Smart Greenhouse")

    response = add(client, superuser, project, lisa)

    assert response.status_code == 422
    assert "Deactivated" in response.json()["detail"]


def test_full_project_refuses_another_member(client: TestClient):
    superuser = ready_to_work(client, "superuser")
    project = create_project(client, superuser, "Drone", minimum=1, maximum=1)
    add(client, superuser, project, create_student(client, superuser, "Lisa"))

    response = add(client, superuser, project, create_student(client, superuser, "Tom"))

    assert response.status_code == 409
    assert "Drone is full" in response.json()["detail"]


def test_adding_twice_is_refused(client: TestClient):
    superuser = ready_to_work(client, "superuser")
    project = create_project(client, superuser, "Drone")
    lisa = create_student(client, superuser, "Lisa")
    add(client, superuser, project, lisa)

    response = add(client, superuser, project, lisa)

    assert response.status_code == 409
    assert "already a Member of Drone" in response.json()["detail"]


def test_moving_needs_confirmation_and_then_happens_in_one_step(client: TestClient):
    superuser = ready_to_work(client, "superuser")
    drone = create_project(client, superuser, "Drone")
    greenhouse = create_project(client, superuser, "Smart Greenhouse")
    lisa = create_student(client, superuser, "Lisa")
    add(client, superuser, drone, lisa)

    unconfirmed = add(client, superuser, greenhouse, lisa)

    assert unconfirmed.status_code == 409
    body = unconfirmed.json()
    assert body["code"] == "move_confirmation_needed"
    assert body["detail"] == (
        "Lisa Peeters is a Member of Drone. Move Lisa Peeters to Smart Greenhouse?"
    )
    assert member_names(client, superuser, drone) == ["Lisa Peeters"]

    confirmed = add(client, superuser, greenhouse, lisa, confirm_move=True)

    assert confirmed.status_code == 200, confirmed.text
    assert member_names(client, superuser, drone) == []
    assert member_names(client, superuser, greenhouse) == ["Lisa Peeters"]


def test_move_into_a_full_project_is_refused(client: TestClient):
    superuser = ready_to_work(client, "superuser")
    drone = create_project(client, superuser, "Drone")
    full = create_project(client, superuser, "Greenhouse", minimum=1, maximum=1)
    lisa = create_student(client, superuser, "Lisa")
    add(client, superuser, drone, lisa)
    add(client, superuser, full, create_student(client, superuser, "Tom"))

    response = add(client, superuser, full, lisa, confirm_move=True)

    assert response.status_code == 409
    assert member_names(client, superuser, drone) == ["Lisa Peeters"]


def test_teacher_removes_a_member(client: TestClient):
    superuser = ready_to_work(client, "superuser")
    project = create_project(client, superuser, "Drone")
    lisa = create_student(client, superuser, "Lisa")
    add(client, superuser, project, lisa)

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
    add(client, superuser, project, lisa)
    client.post(f"/api/users/{lisa}/deactivate", headers=superuser)

    details = client.get(f"/api/projects/{project}", headers=superuser).json()
    another = add(client, superuser, project, create_student(client, superuser, "Tom"))

    assert details["members"][0]["is_active"] is False
    assert details["member_count"] == 1
    assert another.status_code == 409


def test_lowering_the_maximum_below_the_members_is_refused(client: TestClient):
    superuser = ready_to_work(client, "superuser")
    project = create_project(client, superuser, "Drone", minimum=1, maximum=3)
    for name in ("Lisa", "Tom"):
        add(client, superuser, project, create_student(client, superuser, name))

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
    add(client, superuser, project, lisa)

    students = client.get("/api/students", headers=superuser).json()

    by_name = {student["name"]: student for student in students}
    assert by_name["Lisa Peeters"]["project"] == {"id": project, "title": "Drone"}
    assert by_name["Student Account"]["project"] is None


def test_students_cannot_manage_members(client: TestClient):
    superuser = ready_to_work(client, "superuser")
    project = create_project(client, superuser, "Drone")
    student = ready_to_work(client, "student")
    me = client.get("/api/auth/me", headers=student).json()["id"]

    assert add(client, student, project, me).status_code == 403
    assert (
        client.delete(f"/api/projects/{project}/members/{me}", headers=student)
    ).status_code == 403
    assert client.get("/api/students", headers=student).status_code == 403
