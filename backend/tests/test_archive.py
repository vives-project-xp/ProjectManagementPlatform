from fastapi.testclient import TestClient

from tests.conftest import (
    add_member,
    create_project,
    create_student,
    ready_to_work,
    teacher_id,
)


def archive(client: TestClient, headers: dict[str, str], project_id: int):
    return client.post(f"/api/projects/{project_id}/archive", headers=headers)


def restore(client: TestClient, headers: dict[str, str], project_id: int):
    return client.post(f"/api/projects/{project_id}/restore", headers=headers)


def details(client: TestClient, headers: dict[str, str], project_id: int) -> dict:
    return client.get(f"/api/projects/{project_id}", headers=headers).json()


def maker_names(project: dict) -> list[str]:
    return [maker["name"] for maker in project["makers"]]


def test_archiving_stores_makers_frees_students_and_sets_status(client: TestClient):
    superuser = ready_to_work(client, "superuser")
    drone = create_project(client, superuser, "Drone")
    lisa = create_student(client, superuser, "Lisa")
    add_member(client, superuser, drone, lisa)

    response = archive(client, superuser, drone)

    assert response.status_code == 200, response.text
    archived = response.json()
    assert archived["status"] == "archived"
    assert archived["members"] == []
    assert archived["makers"] == [
        {"name": "Lisa Peeters", "programme": "Electronics-ICT", "year": "2"}
    ]
    # The freed Student can join another Project right away, without a move.
    other = create_project(client, superuser, "Greenhouse")
    assert add_member(client, superuser, other, lisa).status_code == 200
    # "Made by" stays the same after the Maker joined another Project.
    assert maker_names(details(client, superuser, drone)) == ["Lisa Peeters"]


def test_archived_project_refuses_edits_and_member_changes(client: TestClient):
    superuser = ready_to_work(client, "superuser")
    drone = create_project(client, superuser, "Drone")
    lisa = create_student(client, superuser, "Lisa")
    add_member(client, superuser, drone, lisa)
    archive(client, superuser, drone)
    tom = create_student(client, superuser, "Tom")

    edit = client.put(
        f"/api/projects/{drone}",
        json={
            "title": "Drone 2",
            "product_owner_id": teacher_id(client, superuser),
            "team_size_min": 1,
            "team_size_max": 3,
        },
        headers=superuser,
    )
    added = add_member(client, superuser, drone, tom)
    removed = client.delete(f"/api/projects/{drone}/members/{lisa}", headers=superuser)
    archived_again = archive(client, superuser, drone)

    for response in (edit, added, removed, archived_again):
        assert response.status_code == 409, response.text
        assert "archived" in response.json()["detail"]
    assert details(client, superuser, drone)["title"] == "Drone"


def test_restore_makes_the_project_active_without_members_keeping_makers(
    client: TestClient,
):
    superuser = ready_to_work(client, "superuser")
    drone = create_project(client, superuser, "Drone")
    lisa = create_student(client, superuser, "Lisa")
    add_member(client, superuser, drone, lisa)
    archive(client, superuser, drone)

    response = restore(client, superuser, drone)

    assert response.status_code == 200, response.text
    restored = response.json()
    assert restored["status"] == "active"
    assert restored["members"] == []
    assert maker_names(restored) == ["Lisa Peeters"]


def test_restoring_an_active_project_is_refused(client: TestClient):
    superuser = ready_to_work(client, "superuser")
    drone = create_project(client, superuser, "Drone")

    response = restore(client, superuser, drone)

    assert response.status_code == 409


def test_rearchiving_appends_makers_without_duplicates(client: TestClient):
    superuser = ready_to_work(client, "superuser")
    drone = create_project(client, superuser, "Drone")
    lisa = create_student(client, superuser, "Lisa")
    tom = create_student(client, superuser, "Tom")
    add_member(client, superuser, drone, lisa)
    archive(client, superuser, drone)
    restore(client, superuser, drone)
    add_member(client, superuser, drone, lisa)
    add_member(client, superuser, drone, tom)

    archived = archive(client, superuser, drone).json()

    assert maker_names(archived) == ["Lisa Peeters", "Tom Peeters"]


def test_archived_title_stays_reserved(client: TestClient):
    superuser = ready_to_work(client, "superuser")
    drone = create_project(client, superuser, "Drone")
    archive(client, superuser, drone)

    response = client.post(
        "/api/projects",
        json={
            "title": "DRONE",
            "product_owner_id": teacher_id(client, superuser),
            "team_size_min": 1,
            "team_size_max": 2,
        },
        headers=superuser,
    )

    assert response.status_code == 409


def test_projects_can_be_filtered_on_status(client: TestClient):
    superuser = ready_to_work(client, "superuser")
    drone = create_project(client, superuser, "Drone")
    create_project(client, superuser, "Greenhouse")
    archive(client, superuser, drone)

    active = client.get("/api/projects?status=active", headers=superuser).json()
    archived = client.get("/api/projects?status=archived", headers=superuser).json()
    everything = client.get("/api/projects", headers=superuser).json()

    assert [project["title"] for project in active] == ["Greenhouse"]
    assert [project["title"] for project in archived] == ["Drone"]
    assert len(everything) == 2


def test_students_cannot_archive_or_restore(client: TestClient):
    superuser = ready_to_work(client, "superuser")
    drone = create_project(client, superuser, "Drone")
    student = ready_to_work(client, "student")

    assert archive(client, student, drone).status_code == 403
    assert restore(client, student, drone).status_code == 403
