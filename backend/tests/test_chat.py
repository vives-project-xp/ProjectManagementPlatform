from fastapi.testclient import TestClient

from tests.conftest import (
    add_member,
    auth,
    create_project,
    create_student,
    ready_to_work,
)


def student_id(client: TestClient, staff) -> int:
    students = client.get("/api/students", headers=staff).json()
    return next(s["id"] for s in students if s["name"] == "Student Account")


def logged_in_student(client: TestClient, superuser, first_name: str) -> dict:
    """A new Student's auth headers, past the password change."""
    user_id = create_student(client, superuser, first_name)
    password = client.post(f"/api/users/{user_id}/reset-password", headers=superuser)
    temporary = password.json()["temporary_password"]
    email = f"{first_name.lower()}@student.vives.be"
    token = client.post(
        "/api/auth/login", json={"email": email, "password": temporary}
    ).json()["access_token"]
    client.post(
        "/api/auth/change-password",
        json={"current_password": temporary, "new_password": "own-password-1"},
        headers=auth(token),
    )
    return auth(token)


def send(client: TestClient, headers, project_id: int, body: str):
    return client.post(
        f"/api/projects/{project_id}/chat/messages",
        json={"body": body},
        headers=headers,
    )


def bodies(client: TestClient, headers, project_id: int, after=None) -> list[str]:
    params = {} if after is None else {"after": after}
    response = client.get(
        f"/api/projects/{project_id}/chat/messages", params=params, headers=headers
    )
    assert response.status_code == 200, response.text
    return [message["body"] for message in response.json()]


def unread(client: TestClient, headers) -> dict:
    return client.get("/api/chats/unread", headers=headers).json()


def test_the_team_and_staff_talk_in_the_project_chat(client: TestClient):
    teacher = ready_to_work(client, "teacher")
    superuser = ready_to_work(client, "superuser")
    drone = create_project(client, teacher, "Drone")
    add_member(client, teacher, drone, student_id(client, teacher))
    student = ready_to_work(client, "student")

    first = send(client, student, drone, "  Who brings the soldering iron?  ")
    send(client, teacher, drone, "I do. See https://vives.be")
    send(client, superuser, drone, "Good luck!")

    assert first.status_code == 201
    assert first.json()["body"] == "Who brings the soldering iron?"
    assert first.json()["author"]["name"] == "Student Account"
    assert first.json()["mine"] is True
    assert bodies(client, student, drone) == [
        "Who brings the soldering iron?",
        "I do. See https://vives.be",
        "Good luck!",
    ]
    assert bodies(client, teacher, drone, after=first.json()["id"]) == [
        "I do. See https://vives.be",
        "Good luck!",
    ]
    chat = client.get(f"/api/projects/{drone}/chat", headers=student).json()
    assert chat == {"project_id": drone, "title": "Drone", "read_only": False}


def test_other_students_have_no_access(client: TestClient):
    teacher = ready_to_work(client, "teacher")
    drone = create_project(client, teacher, "Drone")
    outsider = logged_in_student(client, ready_to_work(client, "superuser"), "Lotte")

    assert send(client, outsider, drone, "Hi").status_code == 403
    response = client.get(f"/api/projects/{drone}/chat/messages", headers=outsider)
    assert response.status_code == 403
    assert response.json()["detail"] == "You don't have access to this chat."
    assert unread(client, outsider) == {"count": 0, "has_chat": False}


def test_a_removed_member_loses_access_and_a_new_one_sees_the_history(
    client: TestClient,
):
    teacher = ready_to_work(client, "teacher")
    drone = create_project(client, teacher, "Drone")
    student = student_id(client, teacher)
    add_member(client, teacher, drone, student)
    headers = ready_to_work(client, "student")
    send(client, teacher, drone, "Welcome")

    client.delete(f"/api/projects/{drone}/members/{student}", headers=teacher)
    removed = client.get(f"/api/projects/{drone}/chat/messages", headers=headers)
    add_member(client, teacher, drone, student)

    assert removed.status_code == 403
    assert bodies(client, headers, drone) == ["Welcome"]


def test_unread_counts_follow_reading(client: TestClient):
    teacher = ready_to_work(client, "teacher")
    superuser = ready_to_work(client, "superuser")
    drone = create_project(client, teacher, "Drone")
    add_member(client, teacher, drone, student_id(client, teacher))
    student = ready_to_work(client, "student")

    send(client, student, drone, "One")
    last = send(client, student, drone, "Two").json()["id"]

    # The sender has nothing Unread; the Product Owner has both messages.
    assert unread(client, student) == {"count": 0, "has_chat": True}
    assert unread(client, teacher) == {"count": 2, "has_chat": True}
    # The Superuser isn't one of the Chat people: listed, not in the badge.
    assert unread(client, superuser)["count"] == 0
    listed = client.get("/api/chats", headers=superuser).json()
    assert listed == [
        {"project_id": drone, "title": "Drone", "unread": 2, "mine": False}
    ]

    read = client.post(
        f"/api/projects/{drone}/chat/read", json={"message_id": last}, headers=teacher
    )
    # Reading never moves back.
    client.post(
        f"/api/projects/{drone}/chat/read", json={"message_id": 0}, headers=teacher
    )

    assert read.status_code == 204
    assert unread(client, teacher)["count"] == 0
    send(client, superuser, drone, "Three")
    assert unread(client, teacher)["count"] == 1
    assert unread(client, student)["count"] == 1


def test_students_see_only_their_own_chat(client: TestClient):
    teacher = ready_to_work(client, "teacher")
    drone = create_project(client, teacher, "Drone")
    create_project(client, teacher, "Robot")
    add_member(client, teacher, drone, student_id(client, teacher))
    student = ready_to_work(client, "student")

    assert [c["title"] for c in client.get("/api/chats", headers=student).json()] == [
        "Drone"
    ]
    assert [c["title"] for c in client.get("/api/chats", headers=teacher).json()] == [
        "Drone",
        "Robot",
    ]


def test_message_length_is_checked(client: TestClient):
    teacher = ready_to_work(client, "teacher")
    drone = create_project(client, teacher, "Drone")

    assert send(client, teacher, drone, "x" * 4000).status_code == 201
    assert send(client, teacher, drone, "x" * 4001).status_code == 422
    assert send(client, teacher, drone, "   ").status_code == 422


def test_an_archived_projects_chat_is_read_only(client: TestClient):
    teacher = ready_to_work(client, "teacher")
    drone = create_project(client, teacher, "Drone")
    send(client, teacher, drone, "Before")

    client.post(f"/api/projects/{drone}/archive", headers=teacher)
    response = send(client, teacher, drone, "After")

    assert response.status_code == 409
    assert response.json()["detail"] == "Drone is archived: its chat is read-only."
    assert bodies(client, teacher, drone) == ["Before"]
    assert client.get(f"/api/projects/{drone}/chat", headers=teacher).json()[
        "read_only"
    ]
