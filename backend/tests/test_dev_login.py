from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from pmp_backend.app import create_app
from pmp_backend.settings import Settings
from tests.conftest import auth, ready_to_work


@pytest.fixture
def dev_client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings.model_copy(update={"dev_login": True}))) as c:
        yield c


def test_dev_login_is_off_by_default(client: TestClient):
    assert client.get("/api/dev-login/users").status_code == 404
    assert client.post("/api/dev-login", json={"user_id": 1}).status_code == 404


def test_dev_login_lists_active_users_by_role(dev_client: TestClient):
    headers = ready_to_work(dev_client, "superuser")
    student = next(
        u["id"]
        for u in dev_client.get("/api/users", headers=headers).json()
        if u["email"] == "student@pmp.local"
    )
    dev_client.post(f"/api/users/{student}/deactivate", headers=headers)

    response = dev_client.get("/api/dev-login/users")

    assert response.status_code == 200
    assert [(u["role"], u["name"]) for u in response.json()] == [
        ("superuser", "Superuser Account"),
        ("teacher", "Teacher Account"),
    ]


def test_dev_login_logs_in_without_a_password(dev_client: TestClient):
    teacher = next(
        u["id"]
        for u in dev_client.get("/api/dev-login/users").json()
        if u["role"] == "teacher"
    )

    response = dev_client.post("/api/dev-login", json={"user_id": teacher})

    assert response.status_code == 200, response.text
    assert response.json()["user"]["email"] == "teacher@pmp.local"
    me = dev_client.get("/api/auth/me", headers=auth(response.json()["access_token"]))
    assert me.json()["email"] == "teacher@pmp.local"


def test_dev_login_refuses_unknown_and_deactivated_users(dev_client: TestClient):
    headers = ready_to_work(dev_client, "superuser")
    teacher = next(
        u["id"]
        for u in dev_client.get("/api/users", headers=headers).json()
        if u["role"] == "teacher"
    )
    dev_client.post(f"/api/users/{teacher}/deactivate", headers=headers)

    unknown = dev_client.post("/api/dev-login", json={"user_id": 9999})
    deactivated = dev_client.post("/api/dev-login", json={"user_id": teacher})

    assert unknown.status_code == 404
    assert deactivated.status_code == 404
