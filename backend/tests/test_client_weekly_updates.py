"""Clients see their Projects' Weekly updates and media (#135)."""

from fastapi.testclient import TestClient

from tests.test_client_projects import client_id, link
from tests.test_clients import logged_in_client
from tests.test_scheduled_posts import Teams, close_week_of


def test_a_client_reads_every_week_without_outcomes(client: TestClient):
    teams = Teams(client)
    project = teams.project("Drone")
    client.put(
        "/api/my-weekly-update",
        json={"text": "We tested the motors."},
        headers=teams.members["Drone"],
    )
    teams.week("Drone")
    close_week_of(project)
    teams.week("Drone", seed=2)
    jan = logged_in_client(client, teams.staff)
    link(client, teams.staff, project, client_id(client, jan))

    response = client.get(f"/api/my-projects/{project}/weekly-updates", headers=jan)

    assert response.status_code == 200, response.text
    weeks = response.json()
    assert [week["is_open"] for week in weeks] == [True, False]
    assert weeks[1]["text"] == "We tested the motors."
    assert all(len(week["media"]) == 1 for week in weeks)
    for hidden in ("suggestion_state", "refusal_reason", "scheduled_for"):
        assert hidden not in weeks[0]
    medium = weeks[0]["media"][0]["id"]
    photo = client.get(f"/api/weekly-media/{medium}", headers=jan)
    assert (photo.status_code, photo.headers["content-type"]) == (200, "image/jpeg")


def test_other_clients_see_nothing(client: TestClient):
    teams = Teams(client)
    project = teams.project("Drone")
    teams.week("Drone")
    medium = client.get("/api/my-weekly-update", headers=teams.members["Drone"]).json()[
        "current"
    ]["media"][0]["id"]
    an = logged_in_client(client, teams.staff, email="an@barco.example")

    weeks = client.get(f"/api/my-projects/{project}/weekly-updates", headers=an)
    photo = client.get(f"/api/weekly-media/{medium}", headers=an)

    assert weeks.status_code == 404
    assert photo.status_code == 403
