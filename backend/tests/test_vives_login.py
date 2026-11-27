"""VIVES login through Authentik (spec #160, #161), against testing.FakeAuthentik."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from pmp_backend.models import Programme, User, VivesLoginSettings
from pmp_backend.testing import FakeAuthentik
from tests.conftest import add_member, auth, create_project, ready_to_work


def switch_on(client: TestClient) -> None:
    """VIVES login on (the screen's Switch on is tested in its own file)."""
    with client.app.state.sessionmaker() as session:
        session.merge(
            VivesLoginSettings(
                id=1,
                group_superuser="pmp-superusers",
                group_teacher="pmp-teachers",
                group_student="pmp-students",
                group_client="pmp-clients",
                programme_claim="programme",
                year_claim="year",
                enabled_at=datetime.now(UTC),
            )
        )
        session.commit()


def log_in(client: TestClient, authentik: FakeAuthentik, nonce="nonce-1", **claims):
    switch_on(client)
    code = authentik.issue(authentik.claims(**claims), nonce=nonce)
    return client.post(
        "/api/auth/vives",
        json={"code": code, "code_verifier": "verifier-1", "nonce": "nonce-1"},
    )


def logged_in(client, authentik, **claims) -> dict:
    response = log_in(client, authentik, **claims)
    assert response.status_code == 200, response.text
    return response.json()


def stored(client: TestClient, email: str) -> User:
    with client.app.state.sessionmaker() as session:
        found = session.query(User).filter_by(email=email).one()
        session.expunge(found)
        return found


def test_start_gives_what_the_frontend_needs(client: TestClient):
    switch_on(client)
    found = client.get("/api/auth/vives/start").json()

    assert found == {
        "configured": True,
        "authorization_endpoint": "https://auth.example.org/application/o/authorize/",
        "client_id": FakeAuthentik.CLIENT_ID,
        "scope": "openid email profile",
        "redirect_uri": "https://10.20.10.33/auth/callback",
    }


def test_the_first_login_creates_the_user_from_authentik(
    client: TestClient, authentik: FakeAuthentik
):
    found = logged_in(client, authentik)

    user = found["user"]
    assert (user["first_name"], user["last_name"]) == ("An", "Student")
    assert user["email"] == "an.student@student.vives.be"
    assert (user["role"], user["programme"], user["year"]) == (
        "student",
        "Electronics-ICT",
        "2",
    )
    assert user["must_change_password"] is False
    me = client.get("/api/auth/me", headers=auth(found["access_token"]))
    assert me.status_code == 200
    assert stored(client, user["email"]).authentik_sub == "sub-1"
    # The code was exchanged with the PKCE verifier and the client secret.
    [sent] = authentik.token_requests
    assert sent["code_verifier"] == "verifier-1"
    assert sent["client_secret"] == FakeAuthentik.CLIENT_SECRET
    assert sent["redirect_uri"] == "https://10.20.10.33/auth/callback"


def test_later_logins_follow_authentik_by_sub(
    client: TestClient, authentik: FakeAuthentik
):
    first = logged_in(client, authentik)["user"]

    again = logged_in(
        client,
        authentik,
        email="an.janssens@student.vives.be",
        given_name="Anna",
        family_name="Janssens",
        year="3",
    )["user"]

    assert again["id"] == first["id"]
    assert (again["first_name"], again["last_name"]) == ("Anna", "Janssens")
    assert again["email"] == "an.janssens@student.vives.be"
    assert again["year"] == "3"


def test_an_existing_email_is_linked(client: TestClient, authentik: FakeAuthentik):
    ready_to_work(client, "superuser")

    found = logged_in(
        client,
        authentik,
        sub="sub-teacher",
        email="Teacher@PMP.local",
        groups=["pmp-teachers"],
        given_name="Teacher",
        family_name="Account",
    )["user"]

    assert found["email"] == "teacher@pmp.local"
    assert found["role"] == "teacher"
    assert stored(client, "teacher@pmp.local").authentik_sub == "sub-teacher"


@pytest.mark.parametrize(
    ("group", "role"),
    [
        ("pmp-superusers", "superuser"),
        ("pmp-teachers", "teacher"),
        ("pmp-clients", "client"),
    ],
)
def test_each_role_group_gives_its_role(
    client: TestClient, authentik: FakeAuthentik, group: str, role: str
):
    found = logged_in(client, authentik, groups=[group, "unrelated"])["user"]

    assert found["role"] == role
    assert found["programme"] is None and found["year"] is None


@pytest.mark.parametrize(
    ("claims", "message"),
    [
        ({"groups": []}, "You have no role on the platform"),
        ({"groups": None}, "You have no role on the platform"),
        (
            {"groups": ["pmp-students", "pmp-teachers"]},
            "more than one platform group in VIVES login (pmp-teachers, pmp-students)",
        ),
        ({"programme": None}, "Your programme or year is missing"),
        ({"year": "7"}, "Your programme or year is missing"),
        ({"email_verified": False}, "no verified email"),
        ({"email": None}, "no verified email"),
    ],
)
def test_wrong_claims_are_refused_with_the_reason(
    client: TestClient, authentik: FakeAuthentik, claims: dict, message: str
):
    response = log_in(client, authentik, **claims)

    assert response.status_code == 403
    assert message in response.json()["detail"]
    with client.app.state.sessionmaker() as session:
        assert session.query(User).filter_by(authentik_sub="sub-1").count() == 0


def test_a_new_programme_is_added_to_the_list(
    client: TestClient, authentik: FakeAuthentik
):
    found = logged_in(client, authentik, programme="Chemistry", year="international")

    assert (found["user"]["programme"], found["user"]["year"]) == (
        "Chemistry",
        "International",
    )
    with client.app.state.sessionmaker() as session:
        assert session.query(Programme).filter_by(name="Chemistry").count() == 1
    # The same Programme in other capitals is the same one.
    other = logged_in(
        client, authentik, sub="sub-2", email="b@vives.be", programme="chemistry"
    )
    assert other["user"]["programme"] == "Chemistry"


def test_a_role_change_is_applied_without_links(
    client: TestClient, authentik: FakeAuthentik
):
    logged_in(client, authentik)

    found = logged_in(client, authentik, groups=["pmp-teachers"])["user"]

    assert found["role"] == "teacher"
    assert found["programme"] is None and found["year"] is None


def test_a_role_change_with_links_is_refused(
    client: TestClient, authentik: FakeAuthentik
):
    staff = ready_to_work(client, "superuser")
    student = logged_in(client, authentik)["user"]
    project = create_project(client, staff, "Drone")
    add_member(client, staff, project, student["id"])

    response = log_in(client, authentik, groups=["pmp-teachers"])

    assert response.status_code == 403
    assert response.json()["detail"] == (
        "Your role changed in VIVES login, but on the platform An Student is a "
        "Member of Drone. Ask the Superuser."
    )
    assert stored(client, student["email"]).role == "student"


def test_a_deactivated_user_is_refused(client: TestClient, authentik: FakeAuthentik):
    staff = ready_to_work(client, "superuser")
    student = logged_in(client, authentik)["user"]
    client.post(f"/api/users/{student['id']}/deactivate", headers=staff)

    response = log_in(client, authentik)

    assert response.status_code == 403
    assert "deactivated" in response.json()["detail"]


@pytest.mark.parametrize(
    "trick",
    [
        "other key",
        "other audience",
        "other issuer",
        "expired",
        "other nonce",
        "used code",
    ],
)
def test_untrusted_tokens_are_refused(
    client: TestClient, authentik: FakeAuthentik, trick: str
):
    claims = {}
    nonce = "nonce-1"
    if trick == "other key":
        authentik.sign_with = "attacker"
    elif trick == "other audience":
        claims = {"aud": "another-app"}
    elif trick == "other issuer":
        claims = {"iss": "https://evil.example.org/"}
    elif trick == "expired":
        claims = {"exp": 1_000_000_000}
    elif trick == "other nonce":
        nonce = "someone-elses-nonce"
    if trick == "used code":
        switch_on(client)
        code = authentik.issue(authentik.claims())
        body = {"code": code, "code_verifier": "v", "nonce": "nonce-1"}
        assert client.post("/api/auth/vives", json=body).status_code == 200
        response = client.post("/api/auth/vives", json=body)
    else:
        response = log_in(client, authentik, nonce=nonce, **claims)

    assert response.status_code == 403, response.text
    with client.app.state.sessionmaker() as session:
        users = session.query(User).filter_by(authentik_sub="sub-1").count()
    assert users == (1 if trick == "used code" else 0)


def test_authentik_down_is_a_503(client: TestClient, authentik: FakeAuthentik):
    switch_on(client)
    authentik.unreachable = True

    assert client.get("/api/auth/vives/start").status_code == 503
    assert log_in(client, authentik).status_code == 503


def test_while_off_there_is_no_vives_login(client: TestClient):
    switch_on(client)
    with client.app.state.sessionmaker() as session:
        session.get(VivesLoginSettings, 1).enabled_at = None
        session.commit()

    assert client.get("/api/auth/vives/start").json()["configured"] is False
    body = {"code": "x", "code_verifier": "v", "nonce": "n"}
    assert client.post("/api/auth/vives", json=body).status_code == 404


def test_without_settings_there_is_no_vives_login(settings, authentik):
    from pmp_backend.app import create_app

    bare = settings.model_copy(update={"authentik_client_secret": None})
    with TestClient(create_app(bare)) as other:
        other.app.state.oidc = authentik
        assert other.get("/api/auth/vives/start").json() == {
            "configured": False,
            "authorization_endpoint": None,
            "client_id": None,
            "scope": None,
            "redirect_uri": None,
        }
        response = other.post(
            "/api/auth/vives",
            json={"code": "x", "code_verifier": "v", "nonce": "n"},
        )
        assert response.status_code == 404
