from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from tests.conftest import add_member, create_project, ready_to_work


def test_project_details_give_each_candidates_rank(client: TestClient):
    staff = ready_to_work(client, "superuser")
    ids = []
    for title in ("Drone", "Robot", "Smart Greenhouse"):
        project = create_project(client, staff, title)
        client.put(
            f"/api/projects/{project}/open-for-choice",
            json={"open": True},
            headers=staff,
        )
        ids.append(project)
    deadline = (datetime.now(UTC) + timedelta(hours=24)).isoformat()
    client.put("/api/top3/round", json={"deadline": deadline}, headers=staff)
    student = ready_to_work(client, "student")
    me = client.get("/api/auth/me", headers=student).json()["id"]
    client.post(
        "/api/my-top3", json={"project_ids": [ids[1], ids[0], ids[2]]}, headers=student
    )

    robot = client.get(f"/api/projects/{ids[1]}", headers=staff).json()
    drone = client.get(f"/api/projects/{ids[0]}", headers=staff).json()

    assert robot["top3_ranks"] == [{"student_id": me, "rank": 1}]
    assert drone["top3_ranks"] == [{"student_id": me, "rank": 2}]
    # Adding the Student (the overview's "Add to …") keeps the usual details.
    added = add_member(client, staff, ids[1], me)
    assert added.status_code == 200, added.text
    assert added.json()["top3_ranks"] == [{"student_id": me, "rank": 1}]


def test_a_project_nobody_chose_has_no_ranks(client: TestClient):
    staff = ready_to_work(client, "teacher")
    project = create_project(client, staff, "Drone")

    details = client.get(f"/api/projects/{project}", headers=staff).json()

    assert details["top3_ranks"] == []
