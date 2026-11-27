"""The VIVES login screen: settings, Setup test, Switch on (spec #160, #162)."""

import pytest
from fastapi.testclient import TestClient

from pmp_backend.app import create_app
from pmp_backend.models import User
from pmp_backend.settings import Settings
from pmp_backend.testing import FakeAuthentik
from tests.conftest import ready_to_work

GROUPS = {
    "superuser": "pmp-superusers",
    "teacher": "pmp-teachers",
    "student": "pmp-students",
    "client": "pmp-clients",
}


@pytest.fixture
def on_screen(settings: Settings, authentik: FakeAuthentik):
    """An app without AUTHENTIK_* in the environment: the screen sets it."""
    bare = settings.model_copy(
        update={
            "authentik_issuer_url": None,
            "authentik_client_id": None,
            "authentik_client_secret": None,
        }
    )
    with TestClient(create_app(bare)) as client:
        client.app.state.oidc = authentik
        yield client


def screen(client, staff) -> dict:
    response = client.get("/api/vives-login", headers=staff)
    assert response.status_code == 200, response.text
    return response.json()


def save(client, staff, **change):
    body = {
        "issuer_url": FakeAuthentik.ISSUER,
        "client_id": FakeAuthentik.CLIENT_ID,
        "client_secret": FakeAuthentik.CLIENT_SECRET,
        "groups": GROUPS,
        "programme_claim": "programme",
        "year_claim": "year",
    } | change
    return client.put("/api/vives-login", json=body, headers=staff)


def setup_test(client, staff, authentik, **claims):
    code = authentik.issue(authentik.claims(**claims), nonce="n-1")
    return client.post(
        "/api/vives-login/setup-test",
        json={"code": code, "code_verifier": "v", "nonce": "n-1"},
        headers=staff,
    )


def superuser_test(client, staff, authentik):
    response = setup_test(
        client,
        staff,
        authentik,
        sub="sub-super",
        email="super@vives.be",
        groups=["pmp-superusers"],
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_the_screen_shows_what_to_copy_and_the_defaults(on_screen: TestClient):
    staff = ready_to_work(on_screen, "superuser")

    found = screen(on_screen, staff)

    assert found["redirect_uri"] == "https://10.20.10.33/auth/callback"
    assert found["scope"] == "openid email profile"
    assert found["groups"] == GROUPS
    assert (found["programme_claim"], found["year_claim"]) == ("programme", "year")
    assert found["from_environment"] is False
    assert found["secret_set"] is False and found["enabled_at"] is None


def test_saving_keeps_the_secret_hidden(on_screen: TestClient):
    staff = ready_to_work(on_screen, "superuser")

    saved = save(on_screen, staff)
    again = save(on_screen, staff, client_secret="", groups=GROUPS | {"client": "x"})

    assert saved.status_code == 200, saved.text
    assert FakeAuthentik.CLIENT_SECRET not in saved.text
    assert saved.json()["secret_set"] is True
    # An empty secret keeps the stored one.
    assert again.json()["secret_set"] is True
    assert again.json()["groups"]["client"] == "x"


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"groups": GROUPS | {"client": " "}}, "Give a group name for every Role."),
        ({"groups": GROUPS | {"client": "pmp-teachers"}}, "its own group"),
        ({"issuer_url": "http://auth.example.org/"}, "starts with https://"),
        ({"year_claim": ""}, "attributes"),
    ],
)
def test_wrong_settings_are_refused(on_screen: TestClient, change: dict, message: str):
    staff = ready_to_work(on_screen, "superuser")

    response = save(on_screen, staff, **change)

    assert response.status_code == 403
    assert message in response.json()["detail"]


def test_check_the_connection(on_screen: TestClient, authentik: FakeAuthentik):
    staff = ready_to_work(on_screen, "superuser")
    before = on_screen.post("/api/vives-login/check", headers=staff)
    save(on_screen, staff)

    found = on_screen.post("/api/vives-login/check", headers=staff)
    authentik.unreachable = True
    down = on_screen.post("/api/vives-login/check", headers=staff)

    assert before.status_code == 403
    assert found.status_code == 200, found.text
    assert found.json()["message"] == (
        f"Connected to {FakeAuthentik.ISSUER}: 1 signing key(s)."
    )
    assert down.status_code == 503


def test_a_setup_test_reports_and_creates_nobody(
    on_screen: TestClient, authentik: FakeAuthentik
):
    staff = ready_to_work(on_screen, "superuser")
    save(on_screen, staff)
    start = on_screen.post("/api/vives-login/test-start", headers=staff).json()

    report = setup_test(on_screen, staff, authentik).json()
    refused = setup_test(on_screen, staff, authentik, groups=[]).json()

    assert start["client_id"] == FakeAuthentik.CLIENT_ID
    assert report == {
        "email": "an.student@student.vives.be",
        "name": "An Student",
        "groups": ["pmp-students"],
        "programme": "Electronics-ICT",
        "year": "2",
        "role": "student",
        "refusal": None,
    }
    assert refused["role"] is None
    assert "You have no role on the platform" in refused["refusal"]
    with on_screen.app.state.sessionmaker() as session:
        assert session.query(User).filter_by(authentik_sub="sub-1").count() == 0


def test_switch_on_needs_a_current_superuser_test(
    on_screen: TestClient, authentik: FakeAuthentik
):
    staff = ready_to_work(on_screen, "superuser")
    save(on_screen, staff)

    without = on_screen.post("/api/vives-login/switch-on", headers=staff)
    setup_test(on_screen, staff, authentik)  # a Student
    as_student = on_screen.post("/api/vives-login/switch-on", headers=staff)
    superuser_test(on_screen, staff, authentik)
    save(on_screen, staff, groups=GROUPS | {"client": "pmp-guests"})
    changed_since = on_screen.post("/api/vives-login/switch-on", headers=staff)

    assert (without.status_code, as_student.status_code, changed_since.status_code) == (
        403,
        403,
        403,
    )
    assert "Superuser Role" in without.json()["detail"]
    assert screen(on_screen, staff)["test_is_current"] is False

    superuser_test(on_screen, staff, authentik)
    done = on_screen.post("/api/vives-login/switch-on", headers=staff)

    assert done.status_code == 200, done.text
    assert done.json()["enabled_at"] is not None
    assert done.json()["enabled_by"] == "Superuser Account"
    # Now the login page offers it, and the screen can't change any more.
    assert on_screen.get("/api/auth/vives/start").json()["configured"] is True
    assert save(on_screen, staff).status_code == 403
    assert setup_test(on_screen, staff, authentik).status_code == 403


def test_environment_settings_win(client: TestClient, authentik: FakeAuthentik):
    staff = ready_to_work(client, "superuser")

    found = screen(client, staff)
    saved = save(client, staff, issuer_url="https://other.example.org/")

    assert found["from_environment"] is True
    assert found["issuer_url"] == FakeAuthentik.ISSUER and found["secret_set"]
    # The environment's connection stays; group names can still be set.
    assert saved.json()["issuer_url"] == FakeAuthentik.ISSUER


@pytest.mark.parametrize("role", ["teacher", "student"])
def test_only_the_superuser(client: TestClient, role: str):
    other = ready_to_work(client, role)

    assert client.get("/api/vives-login", headers=other).status_code == 403
    assert client.post("/api/vives-login/switch-on", headers=other).status_code == 403
