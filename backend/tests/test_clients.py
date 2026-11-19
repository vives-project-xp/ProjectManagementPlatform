"""Clients: the Role, the Organisation and the Superuser's screens (#133)."""

from fastapi.testclient import TestClient

from tests.conftest import auth, create_project, ready_to_work

JAN = {
    "role": "client",
    "first_name": "Jan",
    "last_name": "Peeters",
    "email": "jan@barco.example",
    "organisation": "Barco",
}


def create_client(client: TestClient, staff: dict, **changes) -> dict:
    response = client.post("/api/users", json=JAN | changes, headers=staff)
    assert response.status_code == 201, response.text
    return response.json()


def logged_in_client(client: TestClient, staff: dict, **changes) -> dict[str, str]:
    """A Client who has replaced their Temporary password; their headers."""
    created = create_client(client, staff, **changes)
    token = client.post(
        "/api/auth/login",
        json={"email": created["email"], "password": created["temporary_password"]},
    ).json()["access_token"]
    response = client.post(
        "/api/auth/change-password",
        json={
            "current_password": created["temporary_password"],
            "new_password": "client-own-password",
        },
        headers=auth(token),
    )
    assert response.status_code == 204, response.text
    return auth(token)


def test_the_superuser_creates_a_client_with_an_organisation(client: TestClient):
    staff = ready_to_work(client, "superuser")

    created = create_client(client, staff)

    assert (created["role"], created["organisation"]) == ("client", "Barco")
    assert created["temporary_password"]
    assert (created["programme"], created["year"]) == (None, None)
    listed = client.get("/api/users?role=client", headers=staff).json()
    assert [user["email"] for user in listed] == ["jan@barco.example"]


def test_the_organisation_is_optional_and_only_for_clients(client: TestClient):
    staff = ready_to_work(client, "superuser")

    without = create_client(client, staff, organisation="  ", email="an@x.example")
    teacher = client.post(
        "/api/users",
        json={
            "role": "teacher",
            "first_name": "Els",
            "last_name": "Claes",
            "email": "els@vives.example",
            "organisation": "Barco",
        },
        headers=staff,
    )
    student_fields = client.post(
        "/api/users",
        json=JAN
        | {"email": "p@x.example", "programme": "Electronics-ICT", "year": "2"},
        headers=staff,
    )

    assert without["organisation"] is None
    assert teacher.status_code == 422
    assert "Only Clients have an Organisation" in teacher.text
    assert student_fields.status_code == 422


def test_the_superuser_edits_a_clients_organisation(client: TestClient):
    staff = ready_to_work(client, "superuser")
    created = create_client(client, staff)
    body = {
        "first_name": "Jan",
        "last_name": "Peeters",
        "email": "jan@barco.example",
        "organisation": "Barco Kortrijk",
    }

    changed = client.put(f"/api/users/{created['id']}", json=body, headers=staff)
    cleared = client.put(
        f"/api/users/{created['id']}", json=body | {"organisation": ""}, headers=staff
    )

    assert changed.json()["organisation"] == "Barco Kortrijk"
    assert cleared.json()["organisation"] is None


def test_clients_are_imported_with_one_organisation(client: TestClient):
    staff = ready_to_work(client, "superuser")
    content = (
        b"Firstname,Lastname,email\n"
        b"Jan,Peeters,jan@barco.example\n"
        b"An,Claes,an@barco.example\n"
    )

    response = client.post(
        "/api/users/import",
        files={"file": ("clients.csv", content, "text/csv")},
        data={"role": "client", "organisation": "Barco"},
        headers=staff,
    )

    assert response.status_code == 200, response.text
    assert len(response.json()["created"]) == 2
    listed = client.get("/api/users?role=client", headers=staff).json()
    assert {user["organisation"] for user in listed} == {"Barco"}


def test_a_client_logs_in_and_has_no_github_or_daily_email(client: TestClient):
    staff = ready_to_work(client, "superuser")
    jan = logged_in_client(client, staff)
    me = client.get("/api/auth/me", headers=jan).json()

    github = client.put(
        "/api/me/github-username", json={"github_username": "jan"}, headers=jan
    )
    email = client.put("/api/me/daily-email", json={"daily_email": True}, headers=jan)
    by_superuser = client.put(
        f"/api/users/{me['id']}/github-username",
        json={"github_username": "jan"},
        headers=staff,
    )

    assert me["role"] == "client"
    assert github.status_code == 403
    assert email.status_code == 403
    assert by_superuser.status_code == 422
    assert "Clients have no GitHub username" in by_superuser.text


def test_a_client_is_refused_everything_else(client: TestClient):
    staff = ready_to_work(client, "superuser")
    project = create_project(client, staff, "Drone")
    jan = logged_in_client(client, staff)

    for path in (
        "/api/users",
        "/api/projects",
        f"/api/projects/{project}",
        f"/api/projects/{project}/photo",
        f"/api/projects/{project}/planning",
        "/api/my-project",
        "/api/my-weekly-update",
        "/api/my-top3",
        "/api/planning",
        "/api/post-suggestions",
        "/api/scheduled-posts",
        f"/api/projects/{project}/chat/messages",
    ):
        response = client.get(path, headers=jan)
        assert response.status_code in (403, 404), (path, response.status_code)
    unread = client.get("/api/chats/unread", headers=jan).json()
    assert unread["has_chat"] is False
