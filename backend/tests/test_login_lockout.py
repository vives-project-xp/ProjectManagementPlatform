from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from pmp_backend.app import create_app
from pmp_backend.services.auth import LoginGuard
from pmp_backend.settings import Settings
from tests.conftest import STARTING_ACCOUNTS

LOCKED = "Too many failed attempts. Try again in 15 minutes."


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def guarded_client(settings: Settings, clock: FakeClock) -> Iterator[TestClient]:
    app = create_app(settings)
    app.state.login_guard = LoginGuard(clock=clock)
    with TestClient(app) as client:
        yield client


def log_in(client: TestClient, email: str, password: str):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def fail(client: TestClient, email: str, times: int) -> None:
    for _ in range(times):
        assert log_in(client, email, "wrong-password").status_code == 401


def test_five_wrong_passwords_lock_the_email(guarded_client: TestClient):
    email, password = STARTING_ACCOUNTS["teacher"]
    fail(guarded_client, email, 5)

    response = log_in(guarded_client, email, password)

    assert response.status_code == 429
    assert response.json()["detail"] == LOCKED


def test_four_wrong_passwords_do_not_lock(guarded_client: TestClient):
    email, password = STARTING_ACCOUNTS["teacher"]
    fail(guarded_client, email, 4)

    assert log_in(guarded_client, email, password).status_code == 200


def test_the_lock_is_per_email_and_ignores_case(guarded_client: TestClient):
    email, _ = STARTING_ACCOUNTS["teacher"]
    other_email, other_password = STARTING_ACCOUNTS["student"]
    fail(guarded_client, email.upper(), 5)

    assert log_in(guarded_client, email, "anything").status_code == 429
    assert log_in(guarded_client, other_email, other_password).status_code == 200


def test_the_lock_ends_after_15_minutes(guarded_client: TestClient, clock: FakeClock):
    email, password = STARTING_ACCOUNTS["teacher"]
    fail(guarded_client, email, 5)

    clock.now += 15 * 60 + 1

    assert log_in(guarded_client, email, password).status_code == 200


def test_old_failures_are_forgotten(guarded_client: TestClient, clock: FakeClock):
    email, password = STARTING_ACCOUNTS["teacher"]
    fail(guarded_client, email, 4)
    clock.now += 15 * 60 + 1
    fail(guarded_client, email, 1)

    assert log_in(guarded_client, email, password).status_code == 200


def test_a_successful_login_resets_the_count(guarded_client: TestClient):
    email, password = STARTING_ACCOUNTS["teacher"]
    fail(guarded_client, email, 4)
    assert log_in(guarded_client, email, password).status_code == 200
    fail(guarded_client, email, 4)

    assert log_in(guarded_client, email, password).status_code == 200
