import pytest
from fastapi.testclient import TestClient

from pmp_backend.testing import FakeGitHub
from tests.conftest import auth, login, ready_to_work


def save_own(client: TestClient, headers, username: str | None):
    return client.put(
        "/api/me/github-username", json={"github_username": username}, headers=headers
    )


def user_id(client: TestClient, headers, email: str) -> int:
    users = client.get("/api/users", headers=headers).json()
    return next(user["id"] for user in users if user["email"] == email)


# Looking up an account


def test_looking_up_an_account_shows_its_picture_and_name(
    client: TestClient, github: FakeGitHub
):
    github.add_account("Lisa-P", name="Lisa Peeters")
    headers = ready_to_work(client, "student")

    response = client.get("/api/github/users/lisa-p", headers=headers)

    assert response.status_code == 200, response.text
    assert response.json() == {
        "login": "Lisa-P",
        "name": "Lisa Peeters",
        "avatar_url": "https://avatars.example/Lisa-P.png",
    }


def test_an_unknown_account_is_not_found(client: TestClient):
    headers = ready_to_work(client, "student")

    response = client.get("/api/github/users/nobody-here", headers=headers)

    assert response.status_code == 404
    assert response.json()["detail"] == "No GitHub account is called nobody-here."


def test_an_invalid_username_is_refused(client: TestClient):
    headers = ready_to_work(client, "student")

    response = client.get("/api/github/users/-bad--name", headers=headers)

    assert response.status_code == 422
    assert response.json()["detail"] == "That isn't a valid GitHub username."


def test_github_being_unreachable_is_reported(client: TestClient, github: FakeGitHub):
    github.failing = True
    headers = ready_to_work(client, "student")

    response = client.get("/api/github/users/lisa-p", headers=headers)

    assert response.status_code == 503
    assert response.json()["detail"] == "GitHub can't be reached. Try again later."


# Saving your own


@pytest.mark.parametrize("role", ["student", "teacher", "superuser"])
def test_every_user_saves_their_own_username(
    client: TestClient, github: FakeGitHub, role: str
):
    github.add_account("Lisa-P")
    headers = ready_to_work(client, role)

    response = save_own(client, headers, "lisa-p")

    assert response.status_code == 200, response.text
    # Saved as GitHub spells it.
    assert response.json()["github_username"] == "Lisa-P"
    me = client.get("/api/auth/me", headers=headers).json()
    assert me["github_username"] == "Lisa-P"


def test_an_unknown_account_cannot_be_saved(client: TestClient):
    headers = ready_to_work(client, "student")

    response = save_own(client, headers, "nobody-here")

    assert response.status_code == 404
    assert client.get("/api/auth/me", headers=headers).json()["github_username"] is None


def test_a_username_is_used_by_one_user_only(client: TestClient, github: FakeGitHub):
    github.add_account("Lisa-P")
    teacher = ready_to_work(client, "teacher")
    student = ready_to_work(client, "student")
    save_own(client, teacher, "Lisa-P")

    response = save_own(client, student, "LISA-P")

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "The GitHub username Lisa-P is already used by another User."
    )


def test_saving_the_same_username_again_is_fine(client: TestClient, github: FakeGitHub):
    github.add_account("Lisa-P")
    headers = ready_to_work(client, "student")
    save_own(client, headers, "Lisa-P")

    assert save_own(client, headers, "lisa-p").status_code == 200


def test_a_username_can_be_cleared(client: TestClient, github: FakeGitHub):
    github.add_account("Lisa-P")
    headers = ready_to_work(client, "student")
    save_own(client, headers, "Lisa-P")

    response = save_own(client, headers, None)

    assert response.status_code == 200
    assert response.json()["github_username"] is None


def test_a_temporary_password_must_be_changed_first(
    client: TestClient, github: FakeGitHub
):
    github.add_account("Lisa-P")
    token = login(client, "student")

    assert save_own(client, auth(token), "Lisa-P").status_code == 403


# The Superuser sets anyone's


def test_superuser_sets_and_lists_a_users_username(
    client: TestClient, github: FakeGitHub
):
    github.add_account("Teach-Er")
    headers = ready_to_work(client, "superuser")
    teacher = user_id(client, headers, "teacher@pmp.local")

    response = client.put(
        f"/api/users/{teacher}/github-username",
        json={"github_username": "teach-er"},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    listed = client.get("/api/users?role=teacher", headers=headers).json()
    assert listed[0]["github_username"] == "Teach-Er"


@pytest.mark.parametrize("role", ["teacher", "student"])
def test_only_the_superuser_sets_other_users_username(
    client: TestClient, github: FakeGitHub, role: str
):
    github.add_account("Teach-Er")
    headers = ready_to_work(client, role)

    response = client.put(
        "/api/users/1/github-username",
        json={"github_username": "Teach-Er"},
        headers=headers,
    )

    assert response.status_code == 403
