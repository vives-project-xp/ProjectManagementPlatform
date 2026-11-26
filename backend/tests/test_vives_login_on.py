"""Once VIVES login is on: no password or Test login, people from Authentik,
the Break-glass link and switching off on the VM (spec #160, #163)."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from pmp_backend.app import create_app
from pmp_backend.models import BreakGlassCode
from pmp_backend.services import break_glass
from pmp_backend.settings import Settings
from tests.conftest import STARTING_ACCOUNTS, auth, create_student, ready_to_work
from tests.test_vives_login import switch_on


def password_login(client, role="superuser"):
    email, password = STARTING_ACCOUNTS[role]
    return client.post("/api/auth/login", json={"email": email, "password": password})


def test_no_password_login_once_on(client: TestClient):
    staff = ready_to_work(client, "superuser")
    switch_on(client)

    login = password_login(client)
    change = client.post(
        "/api/auth/change-password",
        json={"current_password": "x", "new_password": "y" * 12},
        headers=staff,
    )

    assert (login.status_code, change.status_code) == (403, 403)
    assert login.json()["detail"] == "Log in with VIVES."


def test_the_test_login_never_works_once_on(settings: Settings):
    with TestClient(
        create_app(settings.model_copy(update={"dev_login": True}))
    ) as client:
        assert client.get("/api/dev-login/users").status_code == 200
        switch_on(client)

        assert client.get("/api/dev-login/users").status_code == 404
        assert client.post("/api/dev-login", json={"user_id": 1}).status_code == 404


def test_people_are_not_created_or_reset_here_once_on(client: TestClient):
    staff = ready_to_work(client, "superuser")
    student = create_student(client, staff, "Anna")
    switch_on(client)

    created = client.post(
        "/api/users",
        json={
            "role": "teacher",
            "first_name": "New",
            "last_name": "Teacher",
            "email": "new.teacher@vives.be",
        },
        headers=staff,
    )
    imported = client.post(
        "/api/users/import",
        files={"file": ("users.csv", b"A,B,a@b.be\n", "text/csv")},
        data={"role": "teacher"},
        headers=staff,
    )
    reset = client.post(f"/api/users/{student}/reset-password", headers=staff)

    assert (created.status_code, imported.status_code, reset.status_code) == (
        409,
        409,
        409,
    )
    assert "VIVES login" in created.json()["detail"]


def test_only_platform_fields_change_once_on(client: TestClient):
    staff = ready_to_work(client, "superuser")
    student = create_student(client, staff, "Anna")
    switch_on(client)
    current = client.get(f"/api/users/{student}", headers=staff).json()
    body = {
        key: current[key]
        for key in ("first_name", "last_name", "email", "programme", "year")
    }

    same = client.put(f"/api/users/{student}", json=body, headers=staff)
    renamed = client.put(
        f"/api/users/{student}", json=body | {"first_name": "Other"}, headers=staff
    )

    assert same.status_code == 200, same.text
    assert renamed.status_code == 409
    assert "change them in Authentik" in renamed.json()["detail"]


def make_link(client: TestClient, email=None) -> str:
    with client.app.state.sessionmaker() as session:
        _, code = break_glass.create(session, email)
    return code


def test_a_break_glass_link_works_once(client: TestClient):
    ready_to_work(client, "superuser")
    switch_on(client)
    code = make_link(client)

    first = client.post("/api/auth/break-glass", json={"code": code})
    again = client.post("/api/auth/break-glass", json={"code": code})
    wrong = client.post("/api/auth/break-glass", json={"code": "guessed"})

    assert first.status_code == 200, first.text
    assert first.json()["user"]["role"] == "superuser"
    me = client.get("/api/auth/me", headers=auth(first.json()["access_token"]))
    assert me.status_code == 200
    assert (again.status_code, wrong.status_code) == (403, 403)
    assert again.json()["detail"] == break_glass.WRONG
    with client.app.state.sessionmaker() as session:
        # Only a hash is kept.
        assert session.query(BreakGlassCode).filter_by(code_hash=code).count() == 0


def test_a_break_glass_link_expires(client: TestClient):
    code = make_link(client)
    with client.app.state.sessionmaker() as session:
        row = session.query(BreakGlassCode).one()
        row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()

    response = client.post("/api/auth/break-glass", json={"code": code})

    assert response.status_code == 403


def test_a_break_glass_link_is_only_for_superusers(client: TestClient):
    teacher_email, _ = STARTING_ACCOUNTS["teacher"]
    ready_to_work(client, "teacher")

    with (
        client.app.state.sessionmaker() as session,
        pytest.raises(break_glass.BreakGlassError),
    ):
        break_glass.create(session, teacher_email)


def test_switching_off_on_the_vm_brings_back_passwords(client: TestClient):
    ready_to_work(client, "superuser")
    switch_on(client)
    assert password_login(client).status_code == 403

    with client.app.state.sessionmaker() as session:
        assert break_glass.switch_off(session) is True
        assert break_glass.switch_off(session) is False

    assert client.get("/api/auth/vives/start").json()["configured"] is False
    email, password = STARTING_ACCOUNTS["superuser"]
    response = client.post(
        "/api/auth/login",
        json={"email": email, "password": f"{password}-changed"},
    )
    assert response.status_code == 200, response.text
