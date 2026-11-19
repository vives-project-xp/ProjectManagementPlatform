"""Clients in their Projects' Chats (#136)."""

from fastapi.testclient import TestClient

from tests.conftest import add_member, create_project, ready_to_work
from tests.test_chat import bodies, send, student_id, unread
from tests.test_client_projects import client_id, link
from tests.test_clients import logged_in_client


def drone_with_a_client(client: TestClient):
    """Drone (Product Owner: the Teacher; Member: the Student) followed by Jan
    (Barco); staff, student and Jan's headers, the Project and Jan's id."""
    staff = ready_to_work(client, "superuser")
    drone = create_project(client, staff, "Drone")
    add_member(client, staff, drone, student_id(client, staff))
    student = ready_to_work(client, "student")
    jan = logged_in_client(client, staff)
    jan_id = client_id(client, jan)
    link(client, staff, drone, jan_id)
    return staff, student, jan, drone, jan_id


def test_a_client_talks_in_the_chat_with_the_whole_history(client: TestClient):
    staff, student, jan, drone, jan_id = drone_with_a_client(client)
    send(client, student, drone, "Before Jan read along")

    assert send(client, jan, drone, "Hello team!").status_code == 201

    assert bodies(client, jan, drone) == ["Before Jan read along", "Hello team!"]
    chats = client.get("/api/chats", headers=jan).json()
    assert [(c["title"], c["mine"]) for c in chats] == [("Drone", True)]
    people = client.get(f"/api/projects/{drone}/chat/people", headers=jan).json()
    assert {"name": "Jan Peeters (Barco)", "kind": "Client"} in [
        {"name": p["name"], "kind": p["kind"]} for p in people
    ]
    messages = client.get(f"/api/projects/{drone}/chat/messages", headers=student)
    assert messages.json()[-1]["author"]["name"] == "Jan Peeters (Barco)"


def test_unread_and_mentions_count_for_a_client(client: TestClient):
    staff, student, jan, drone, jan_id = drone_with_a_client(client)
    client.put(
        f"/api/projects/{drone}/client-product-owner",
        json={"client_id": jan_id},
        headers=staff,
    )

    send(client, student, drone, "@Jan Peeters can you look at the demo?")

    badge = unread(client, jan)
    assert (badge["count"], badge["mentioned"], badge["has_chat"]) == (1, True, True)
    people = client.get(f"/api/projects/{drone}/chat/people", headers=student).json()
    assert {"name": "Jan Peeters (Barco)", "kind": "Client Product Owner"} in [
        {"name": p["name"], "kind": p["kind"]} for p in people
    ]


def test_a_client_cant_leave_add_guests_or_delete_others(client: TestClient):
    staff, student, jan, drone, jan_id = drone_with_a_client(client)
    message = send(client, student, drone, "Our message").json()["id"]

    leave = client.post(f"/api/projects/{drone}/chat/leave", headers=jan)
    guest = client.post(
        f"/api/projects/{drone}/chat/guests",
        json={"user_id": client_id(client, staff)},
        headers=jan,
    )
    deleted = client.delete(f"/api/chat/messages/{message}", headers=jan)
    as_guest = client.post(
        f"/api/projects/{drone}/chat/guests", json={"user_id": jan_id}, headers=staff
    )

    assert leave.status_code == 404
    assert guest.status_code == 403
    assert deleted.status_code == 403
    assert as_guest.status_code == 409


def test_unlinking_or_archiving_ends_a_clients_chat(client: TestClient):
    staff, student, jan, drone, jan_id = drone_with_a_client(client)
    send(client, jan, drone, "My message stays")
    robot = create_project(client, staff, "Robot")
    link(client, staff, robot, jan_id)

    client.delete(f"/api/projects/{drone}/clients/{jan_id}", headers=staff)

    assert (
        client.get(f"/api/projects/{drone}/chat/messages", headers=jan).status_code
        == 403
    )
    assert bodies(client, student, drone) == ["My message stays"]
    client.post(f"/api/projects/{robot}/archive", headers=staff)
    assert (
        client.get(f"/api/projects/{robot}/chat/messages", headers=jan).status_code
        == 403
    )
    assert client.get("/api/chats", headers=jan).json() == []
