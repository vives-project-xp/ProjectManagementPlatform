import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update

from pmp_backend.app import create_app
from pmp_backend.models import User
from pmp_backend.settings import Settings
from tests.conftest import (
    STARTING_ACCOUNTS,
    TEST_DATABASE_URL,
    TEST_JWT_SECRET,
    auth,
    login,
)

GENERIC_LOGIN_ERROR = "Incorrect email or password."


def change_password(client: TestClient, role: str, new_password: str) -> None:
    token = login(client, role)
    _, current_password = STARTING_ACCOUNTS[role]
    response = client.post(
        "/api/auth/change-password",
        json={"current_password": current_password, "new_password": new_password},
        headers=auth(token),
    )
    assert response.status_code == 204, response.text


def test_starting_account_can_log_in(client: TestClient):
    email, password = STARTING_ACCOUNTS["teacher"]

    response = client.post(
        "/api/auth/login", json={"email": email, "password": password}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["user"]["email"] == "teacher@pmp.local"
    assert body["user"]["role"] == "teacher"
    assert body["user"]["must_change_password"] is True


def test_email_is_case_insensitive_at_login(client: TestClient):
    _, password = STARTING_ACCOUNTS["student"]

    response = client.post(
        "/api/auth/login", json={"email": " Student@PMP.Local ", "password": password}
    )

    assert response.status_code == 200


def test_wrong_password_and_unknown_email_get_the_same_generic_error(
    client: TestClient,
):
    email, _ = STARTING_ACCOUNTS["teacher"]

    wrong_password = client.post(
        "/api/auth/login", json={"email": email, "password": "not-the-password"}
    )
    unknown_email = client.post(
        "/api/auth/login", json={"email": "nobody@pmp.local", "password": "whatever1"}
    )

    for response in (wrong_password, unknown_email):
        assert response.status_code == 401
        assert response.json()["detail"] == GENERIC_LOGIN_ERROR


def test_deactivated_user_gets_the_generic_error_and_loses_their_session(
    client: TestClient,
):
    token = login(client, "teacher")
    email, password = STARTING_ACCOUNTS["teacher"]
    with client.app.state.sessionmaker() as session:
        session.execute(update(User).where(User.email == email).values(is_active=False))
        session.commit()

    response = client.post(
        "/api/auth/login", json={"email": email, "password": password}
    )

    assert response.status_code == 401
    assert response.json()["detail"] == GENERIC_LOGIN_ERROR
    assert client.get("/api/auth/me", headers=auth(token)).status_code == 401


def test_restart_never_overwrites_a_changed_password(settings: Settings):
    with TestClient(create_app(settings)) as client:
        change_password(client, "superuser", "my-own-password")

    # A second start (a redeploy) reads the same logins file again.
    with TestClient(create_app(settings)) as client:
        email, original_password = STARTING_ACCOUNTS["superuser"]
        old = client.post(
            "/api/auth/login", json={"email": email, "password": original_password}
        )
        new = client.post(
            "/api/auth/login", json={"email": email, "password": "my-own-password"}
        )

        assert old.status_code == 401
        assert new.status_code == 200
        assert new.json()["user"]["must_change_password"] is False


def test_missing_logins_file_is_logged_not_fatal(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
):
    settings = Settings(
        database_url=TEST_DATABASE_URL,
        jwt_secret=TEST_JWT_SECRET,
        logins_file=tmp_path / "missing.txt",
    )

    with caplog.at_level(logging.WARNING), TestClient(create_app(settings)) as client:
        assert client.get("/api/health").status_code == 200

    assert "No logins file" in caplog.text


def test_me_says_whether_the_password_must_change(client: TestClient):
    token = login(client, "student")

    response = client.get("/api/auth/me", headers=auth(token))

    assert response.status_code == 200
    assert response.json()["email"] == "student@pmp.local"
    assert response.json()["must_change_password"] is True


def test_other_endpoints_refuse_until_the_password_is_changed(client: TestClient):
    token = login(client, "teacher")

    before = client.get("/api/programmes", headers=auth(token))
    change_password(client, "teacher", "a-brand-new-password")
    after = client.get("/api/programmes", headers=auth(token))

    assert before.status_code == 403
    assert after.status_code == 200
    assert (
        client.get("/api/auth/me", headers=auth(token)).json()["must_change_password"]
        is False
    )


@pytest.mark.parametrize(
    ("current_password", "new_password", "message"),
    [
        ("wrong-current", "long-enough-1", "current password is incorrect"),
        ("teacher-secret-1", "short", "at least 8 characters"),
    ],
)
def test_change_password_rules(
    client: TestClient, current_password: str, new_password: str, message: str
):
    token = login(client, "teacher")

    response = client.post(
        "/api/auth/change-password",
        json={"current_password": current_password, "new_password": new_password},
        headers=auth(token),
    )

    assert response.status_code == 422
    assert message in response.json()["detail"]


def test_logout_works_with_a_temporary_password(client: TestClient):
    token = login(client, "student")

    assert client.post("/api/auth/logout", headers=auth(token)).status_code == 204


def test_missing_or_invalid_token_is_refused(client: TestClient):
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers=auth("not-a-token")).status_code == 401


def test_expired_token_is_refused(logins_file: Path):
    settings = Settings(
        database_url=TEST_DATABASE_URL,
        jwt_secret=TEST_JWT_SECRET,
        logins_file=logins_file,
        token_lifetime_minutes=-1,
    )
    with TestClient(create_app(settings)) as client:
        token = login(client, "teacher")

        response = client.get("/api/auth/me", headers=auth(token))

    assert response.status_code == 401
    assert "expired" in response.json()["detail"]
