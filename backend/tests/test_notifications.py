"""Browser notifications for Chat messages (spec #145, #148)."""

from fastapi.testclient import TestClient

from tests.conftest import add_member, create_project, ready_to_work
from tests.test_chat import send, student_id


def look(client: TestClient, headers, since=None) -> dict:
    params = {} if since is None else {"since": since}
    response = client.get("/api/notifications", params=params, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def drone(client: TestClient) -> tuple[dict, dict, int]:
    teacher = ready_to_work(client, "teacher")
    project = create_project(client, teacher, "Drone")
    add_member(client, teacher, project, student_id(client, teacher))
    return teacher, ready_to_work(client, "student"), project


def test_new_messages_of_others_in_own_chats_notify(client: TestClient):
    teacher, student, project = drone(client)
    first = look(client, student)
    assert first["chat"] == []

    send(client, teacher, project, "Meeting moved to 14:00, " + "x" * 200)
    send(client, student, project, "My own message")
    found = look(client, student, first["latest"])

    [message] = found["chat"]
    assert message["project_id"] == project
    assert message["project_title"] == "Drone"
    assert message["author"] == "Teacher Account"
    assert message["text"].startswith("Meeting moved to 14:00")
    assert len(message["text"]) == 100
    assert message["mentions_me"] is False
    # The next look starts after what was seen.
    assert look(client, student, found["latest"])["chat"] == []


def test_a_mention_is_marked(client: TestClient):
    teacher, student, project = drone(client)
    since = look(client, student)["latest"]

    send(client, teacher, project, "@Student Account can you check the motors?")

    [message] = look(client, student, since)["chat"]
    assert message["mentions_me"] is True


def test_deleted_messages_and_other_chats_never_notify(client: TestClient):
    teacher, student, project = drone(client)
    superuser = ready_to_work(client, "superuser")
    other = create_project(client, teacher, "Robot")
    since = look(client, student)["latest"]

    gone = send(client, teacher, project, "Oops").json()["id"]
    client.delete(f"/api/chat/messages/{gone}", headers=teacher)
    send(client, teacher, other, "Not your Project")

    assert look(client, student, since)["chat"] == []
    # The Superuser reads every Chat but is one of the Chat people of none.
    assert look(client, superuser, since)["chat"] == []
    # The Teacher is the Product Owner of both.
    send(client, student, project, "Done!")
    assert [m["text"] for m in look(client, teacher, since)["chat"]] == ["Done!"]


def test_the_switch_turns_them_off(client: TestClient):
    teacher, student, project = drone(client)
    since = look(client, student)["latest"]

    switched = client.put(
        "/api/me/notifications", json={"chat_notifications": False}, headers=student
    )
    send(client, teacher, project, "Hello")

    assert switched.status_code == 200, switched.text
    assert switched.json()["chat_notifications"] is False
    assert switched.json()["tiktok_alerts"] is True
    assert look(client, student, since)["chat"] == []
    me = client.get("/api/auth/me", headers=student).json()
    assert me["chat_notifications"] is False
