"""Clients following Projects and their read-only Project pages (#134)."""

from fastapi.testclient import TestClient

from tests.conftest import add_member, create_project, create_student, ready_to_work
from tests.test_clients import create_client, logged_in_client


def link(client: TestClient, staff: dict, project: int, client_id: int):
    return client.post(
        f"/api/projects/{project}/clients", json={"client_id": client_id}, headers=staff
    )


def client_id(client: TestClient, headers: dict) -> int:
    return client.get("/api/auth/me", headers=headers).json()["id"]


def test_staff_link_a_client_and_label_them(client: TestClient):
    staff = ready_to_work(client, "superuser")
    teacher = ready_to_work(client, "teacher")
    drone = create_project(client, staff, "Drone")
    jan = create_client(client, staff)
    an = create_client(
        client, staff, first_name="An", email="an@barco.example", organisation=None
    )

    assert link(client, teacher, drone, jan["id"]).status_code == 200
    again = link(client, teacher, drone, jan["id"])
    link(client, teacher, drone, an["id"])
    labelled = client.put(
        f"/api/projects/{drone}/client-product-owner",
        json={"client_id": jan["id"]},
        headers=teacher,
    )
    moved = client.put(
        f"/api/projects/{drone}/client-product-owner",
        json={"client_id": an["id"]},
        headers=teacher,
    )

    assert again.status_code == 409
    assert [c["name"] for c in labelled.json()["clients"]] == [
        "An Peeters",
        "Jan Peeters (Barco)",
    ]
    assert [c["is_client_product_owner"] for c in labelled.json()["clients"]] == [
        False,
        True,
    ]
    # One label per Project: giving it to An takes it from Jan.
    assert [c["is_client_product_owner"] for c in moved.json()["clients"]] == [
        True,
        False,
    ]
    removed = client.delete(
        f"/api/projects/{drone}/clients/{an['id']}", headers=teacher
    )
    assert [c["name"] for c in removed.json()["clients"]] == ["Jan Peeters (Barco)"]
    assert not removed.json()["clients"][0]["is_client_product_owner"]


def test_only_staff_link_and_only_clients_can_be_linked(client: TestClient):
    staff = ready_to_work(client, "superuser")
    student = ready_to_work(client, "student")
    drone = create_project(client, staff, "Drone")
    jan = create_client(client, staff)
    teacher_id = client_id(client, ready_to_work(client, "teacher"))

    assert link(client, student, drone, jan["id"]).status_code == 403
    assert link(client, staff, drone, teacher_id).status_code == 404
    client.post(f"/api/users/{jan['id']}/deactivate", headers=staff)
    assert link(client, staff, drone, jan["id"]).status_code == 422
    picker = client.get("/api/clients", headers=staff).json()
    assert picker == []


def test_a_client_sees_only_the_projects_they_follow(client: TestClient):
    staff = ready_to_work(client, "superuser")
    drone = create_project(client, staff, "Drone")
    robot = create_project(client, staff, "Robot")
    lisa = create_student(client, staff, "Lisa")
    add_member(client, staff, drone, lisa)
    jan = logged_in_client(client, staff)
    link(client, staff, drone, client_id(client, jan))

    listed = client.get("/api/my-projects", headers=jan).json()
    page = client.get(f"/api/my-projects/{drone}", headers=jan)
    other = client.get(f"/api/my-projects/{robot}", headers=jan)
    planning = client.get(f"/api/my-projects/{drone}/planning", headers=jan)
    photo_elsewhere = client.get(f"/api/projects/{robot}/photo", headers=jan)

    assert [(p["title"], p["status"]) for p in listed] == [("Drone", "active")]
    body = page.json()
    assert body["members"] == ["Lisa Peeters"]
    assert body["product_owner"] == "Teacher Account"
    assert [c["name"] for c in body["clients"]] == ["Jan Peeters (Barco)"]
    assert "email" not in page.text
    assert "trello" not in page.text
    assert other.status_code == 404
    assert planning.status_code == 200
    assert photo_elsewhere.status_code == 403


def test_archived_projects_stay_and_lock_their_clients(client: TestClient):
    staff = ready_to_work(client, "superuser")
    drone = create_project(client, staff, "Drone")
    jan = logged_in_client(client, staff)
    jan_id = client_id(client, jan)
    link(client, staff, drone, jan_id)

    client.post(f"/api/projects/{drone}/archive", headers=staff)

    listed = client.get("/api/my-projects", headers=jan).json()
    assert [(p["title"], p["status"]) for p in listed] == [("Drone", "archived")]
    assert client.get(f"/api/my-projects/{drone}", headers=jan).status_code == 200
    removed = client.delete(f"/api/projects/{drone}/clients/{jan_id}", headers=staff)
    assert removed.status_code in (409, 422)
    client.post(f"/api/projects/{drone}/restore", headers=staff)
    assert client.get("/api/my-projects", headers=jan).json()[0]["status"] == "active"


def test_a_linked_client_is_deactivated_not_deleted(client: TestClient):
    staff = ready_to_work(client, "superuser")
    drone = create_project(client, staff, "Drone")
    jan = create_client(client, staff)
    link(client, staff, drone, jan["id"])

    refused = client.delete(f"/api/users/{jan['id']}", headers=staff)

    assert refused.status_code == 409
    assert "follows Drone" in refused.text
    client.delete(f"/api/projects/{drone}/clients/{jan['id']}", headers=staff)
    assert client.delete(f"/api/users/{jan['id']}", headers=staff).status_code == 204


def test_deleting_a_project_removes_its_client_links(client: TestClient):
    staff = ready_to_work(client, "superuser")
    drone = create_project(client, staff, "Drone")
    jan = logged_in_client(client, staff)
    link(client, staff, drone, client_id(client, jan))

    assert client.delete(f"/api/projects/{drone}", headers=staff).status_code == 204

    assert client.get("/api/my-projects", headers=jan).json() == []


def test_the_team_and_top3_see_the_clients(client: TestClient):
    staff = ready_to_work(client, "superuser")
    student = ready_to_work(client, "student")
    drone = create_project(client, staff, "Drone")
    jan = create_client(client, staff)
    link(client, staff, drone, jan["id"])
    client.put(
        f"/api/projects/{drone}/open-for-choice", json={"open": True}, headers=staff
    )

    top3 = client.get("/api/my-top3", headers=student).json()
    me = client_id(client, student)
    add_member(client, staff, drone, me)
    mine = client.get("/api/my-project", headers=student).json()

    assert top3["projects"][0]["client_organisations"] == ["Barco"]
    assert [c["name"] for c in mine["clients"]] == ["Jan Peeters (Barco)"]
