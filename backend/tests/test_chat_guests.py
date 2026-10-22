from fastapi.testclient import TestClient

from tests.conftest import add_member, create_project, ready_to_work
from tests.test_chat import logged_in_student, send, student_id, unread


def guests_url(project_id: int) -> str:
    return f"/api/projects/{project_id}/chat/guests"


def people(client: TestClient, headers, project_id: int) -> list[tuple[str, str]]:
    response = client.get(f"/api/projects/{project_id}/chat/people", headers=headers)
    assert response.status_code == 200, response.text
    return [(person["name"], person["kind"]) for person in response.json()]


def user_id(client: TestClient, superuser, name: str) -> int:
    users = client.get("/api/users", headers=superuser).json()
    return next(u["id"] for u in users if f"{u['first_name']} {u['last_name']}" == name)


def test_staff_add_a_guest_who_then_reads_writes_and_leaves(client: TestClient):
    teacher = ready_to_work(client, "teacher")
    superuser = ready_to_work(client, "superuser")
    drone = create_project(client, teacher, "Drone")
    add_member(client, teacher, drone, student_id(client, teacher))
    lotte = logged_in_student(client, superuser, "Lotte")
    lotte_id = user_id(client, superuser, "Lotte Peeters")
    send(client, teacher, drone, "Before Lotte joined")

    candidates = client.get(f"{guests_url(drone)}/candidates", headers=teacher).json()
    added = client.post(guests_url(drone), json={"user_id": lotte_id}, headers=teacher)

    # By last name; the Product Owner and the Member are already in.
    assert [c["name"] for c in candidates] == ["Superuser Account", "Lotte Peeters"]
    assert added.status_code == 201
    assert people(client, lotte, drone) == [
        ("Teacher Account", "Product Owner"),
        ("Student Account", "Member"),
        ("Lotte Peeters", "Guest"),
    ]
    chat = client.get(f"/api/projects/{drone}/chat", headers=lotte).json()
    assert chat["is_guest"] is True and chat["can_manage_guests"] is False
    # A Guest sees the whole history and counts the chat as theirs.
    assert unread(client, lotte) == {"count": 1, "has_chat": True}
    assert send(client, lotte, drone, "Hi, I'm helping out").status_code == 201

    left = client.delete(f"{guests_url(drone)}/{lotte_id}", headers=lotte)

    assert left.status_code == 204
    assert send(client, lotte, drone, "Still here?").status_code == 403
    assert unread(client, lotte) == {"count": 0, "has_chat": False}


def test_members_cannot_add_or_remove_guests(client: TestClient):
    teacher = ready_to_work(client, "teacher")
    superuser = ready_to_work(client, "superuser")
    drone = create_project(client, teacher, "Drone")
    add_member(client, teacher, drone, student_id(client, teacher))
    student = ready_to_work(client, "student")
    logged_in_student(client, superuser, "Lotte")
    lotte_id = user_id(client, superuser, "Lotte Peeters")

    refused = client.post(
        guests_url(drone), json={"user_id": lotte_id}, headers=student
    )
    client.post(guests_url(drone), json={"user_id": lotte_id}, headers=superuser)
    removal = client.delete(f"{guests_url(drone)}/{lotte_id}", headers=student)

    assert refused.status_code == 403
    assert refused.json()["detail"] == (
        "Only the Product Owner, Teachers and the Superuser add or remove Guests."
    )
    assert removal.status_code == 403
    removed = client.delete(f"{guests_url(drone)}/{lotte_id}", headers=superuser)
    assert removed.status_code == 204
    assert ("Lotte Peeters", "Guest") not in people(client, teacher, drone)


def test_who_cannot_be_added(client: TestClient):
    teacher = ready_to_work(client, "teacher")
    superuser = ready_to_work(client, "superuser")
    drone = create_project(client, teacher, "Drone")
    member = student_id(client, teacher)
    add_member(client, teacher, drone, member)
    logged_in_student(client, superuser, "Lotte")
    lotte_id = user_id(client, superuser, "Lotte Peeters")
    client.post(f"/api/users/{lotte_id}/deactivate", headers=superuser)

    as_member = client.post(
        guests_url(drone), json={"user_id": member}, headers=teacher
    )
    deactivated = client.post(
        guests_url(drone), json={"user_id": lotte_id}, headers=teacher
    )
    teacher_id = user_id(client, superuser, "Teacher Account")
    product_owner = client.post(
        guests_url(drone), json={"user_id": teacher_id}, headers=superuser
    )

    assert as_member.status_code == 409
    assert as_member.json()["detail"] == "Student Account is already in this chat."
    assert deactivated.status_code == 422
    assert product_owner.status_code == 409


def test_a_teacher_counts_guest_chats_as_theirs(client: TestClient):
    teacher = ready_to_work(client, "teacher")
    superuser = ready_to_work(client, "superuser")
    drone = create_project(client, teacher, "Drone")
    robot = create_project(client, teacher, "Robot")
    superuser_id = user_id(client, superuser, "Superuser Account")
    send(client, teacher, drone, "For the team")
    send(client, teacher, robot, "Also for a team")

    before = client.get("/api/chats", params={"mine": True}, headers=superuser).json()
    client.post(guests_url(drone), json={"user_id": superuser_id}, headers=teacher)
    after = client.get("/api/chats", params={"mine": True}, headers=superuser).json()

    assert before == []
    assert [(c["title"], c["unread"]) for c in after] == [("Drone", 1)]
    assert unread(client, superuser)["count"] == 1
    # Without the filter, every chat is still listed.
    assert len(client.get("/api/chats", headers=superuser).json()) == 2


def test_a_student_guest_without_a_project_has_a_chat(client: TestClient):
    teacher = ready_to_work(client, "teacher")
    superuser = ready_to_work(client, "superuser")
    drone = create_project(client, teacher, "Drone")
    robot = create_project(client, teacher, "Robot")
    add_member(client, teacher, robot, student_id(client, teacher))
    student = ready_to_work(client, "student")
    lotte = logged_in_student(client, superuser, "Lotte")
    lotte_id = user_id(client, superuser, "Lotte Peeters")
    student_user = student_id(client, teacher)

    assert unread(client, lotte)["has_chat"] is False
    client.post(guests_url(drone), json={"user_id": lotte_id}, headers=teacher)
    client.post(guests_url(drone), json={"user_id": student_user}, headers=teacher)

    assert [c["title"] for c in client.get("/api/chats", headers=lotte).json()] == [
        "Drone"
    ]
    # A Member of Robot who is also a Guest in Drone has both chats.
    assert [c["title"] for c in client.get("/api/chats", headers=student).json()] == [
        "Drone",
        "Robot",
    ]


def test_archiving_ends_guest_access(client: TestClient):
    teacher = ready_to_work(client, "teacher")
    superuser = ready_to_work(client, "superuser")
    drone = create_project(client, teacher, "Drone")
    lotte = logged_in_student(client, superuser, "Lotte")
    lotte_id = user_id(client, superuser, "Lotte Peeters")
    client.post(guests_url(drone), json={"user_id": lotte_id}, headers=teacher)

    client.post(f"/api/projects/{drone}/archive", headers=teacher)

    response = client.get(f"/api/projects/{drone}/chat/messages", headers=lotte)
    assert response.status_code == 403
    assert people(client, teacher, drone) == [("Teacher Account", "Product Owner")]
    added = client.post(guests_url(drone), json={"user_id": lotte_id}, headers=teacher)
    assert added.status_code == 409
