from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from pmp_backend.services.daily_email import send_daily_emails
from pmp_backend.settings import Settings
from pmp_backend.testing import FakeMailer
from tests.conftest import add_member, create_project, create_student, ready_to_work

BRUSSELS = ZoneInfo("Europe/Brussels")
TEACHER = "teacher@pmp.local"
LISA = "lisa@student.vives.be"


def today() -> date:
    return datetime.now(BRUSSELS).date()


def at(hour: int, minute: int = 0, days: int = 0) -> datetime:
    d = today() + timedelta(days=days)
    return datetime(d.year, d.month, d.day, hour, minute, tzinfo=BRUSSELS)


@pytest.fixture
def mail_settings(settings: Settings) -> Settings:
    return settings.model_copy(update={"smtp_host": "smtp.test"})


@pytest.fixture
def run(client: TestClient, mailer: FakeMailer, mail_settings: Settings):
    """Run the daily job at a given moment (default: 08:31 today)."""

    def run_at(moment: datetime | None = None, settings: Settings = mail_settings):
        with client.app.state.sessionmaker() as session:
            return send_daily_emails(session, mailer, settings, moment or at(8, 31))

    return run_at


@pytest.fixture
def drone(client: TestClient):
    """Drone (Product Owner: the Teacher starting account) with Member Lisa."""
    staff = ready_to_work(client, "superuser")
    project = create_project(client, staff, "Drone")
    add_member(client, staff, project, create_student(client, staff, "Lisa"))
    return staff, project


def add_deadline(client, staff, project_id, title, due: datetime):
    path = f"/api/projects/{project_id}/deadlines" if project_id else "/api/deadlines"
    response = client.post(
        path, json={"title": title, "due_at": due.isoformat()}, headers=staff
    )
    assert response.status_code == 201, response.text


def test_members_and_the_product_owner_get_one_email(
    client: TestClient, mailer: FakeMailer, run, drone
):
    staff, project = drone
    add_deadline(client, staff, project, "Poster due", at(23, 59))
    add_deadline(client, staff, None, "Final presentation", at(14))
    client.post(
        f"/api/projects/{project}/meetings",
        json={
            "starts_at": at(10).isoformat(),
            "ends_at": at(11).isoformat(),
            "place": "B2.14",
            "note": "Bring the demo",
        },
        headers=staff,
    )
    add_deadline(client, staff, project, "Tomorrow", at(12, days=1))

    sent = run()

    assert sent == 2
    assert sorted(email.to for email in mailer.sent) == [LISA, TEACHER]
    email = mailer.to(LISA)[0]
    assert email.subject == f"Your planning for today, {today():%A %d/%m/%Y}"
    assert email.body.splitlines()[:7] == [
        "Hello Lisa,",
        "",
        "Today for Drone:",
        "- 10:00–11:00 Meeting · B2.14",
        "  Bring the demo",
        "- 14:00 Deadline: Final presentation",
        "- 23:59 Deadline: Poster due",
    ]
    assert "See your planning on https://10.20.10.33" in email.body
    # The Superuser is on no Project and gets nothing.
    assert not mailer.to("superuser@pmp.local")


def test_the_weekly_meeting_counts_unless_skipped(
    client: TestClient, mailer: FakeMailer, run, drone
):
    staff, project = drone
    client.put(
        f"/api/projects/{project}/weekly-slot",
        json={
            "weekday": today().weekday(),
            "starts": "10:00",
            "ends": "10:30",
            "place": "B2.14",
        },
        headers=staff,
    )
    client.post(
        f"/api/projects/{project}/weekly-slot/skips/{today() + timedelta(days=7)}",
        headers=staff,
    )

    run()
    run(at(8, 31, days=7))

    assert [e.body.splitlines()[3] for e in mailer.to(LISA)] == [
        "- 10:00–10:30 Weekly meeting · B2.14"
    ]


def test_nothing_on_a_quiet_day(client: TestClient, mailer: FakeMailer, run, drone):
    staff, project = drone
    add_deadline(client, staff, project, "Tomorrow", at(12, days=1))

    assert run() == 0
    assert mailer.sent == []


def test_only_between_0830_and_1800(client: TestClient, mailer: FakeMailer, run, drone):
    staff, project = drone
    add_deadline(client, staff, project, "Poster due", at(23, 59))

    early = run(at(8, 29))
    late = run(at(18, 0))
    on_time = run(at(17, 59))

    assert (early, late, on_time) == (0, 0, 2)


def test_never_twice_a_day(client: TestClient, mailer: FakeMailer, run, drone):
    staff, project = drone
    add_deadline(client, staff, project, "Poster due", at(23, 59))

    run()
    again = run(at(12))

    assert again == 0
    assert len(mailer.to(LISA)) == 1


def test_switched_off_users_get_nothing(
    client: TestClient, mailer: FakeMailer, run, drone
):
    staff, project = drone
    add_deadline(client, staff, project, "Poster due", at(23, 59))
    teacher = ready_to_work(client, "teacher")

    switched = client.put(
        "/api/me/daily-email", json={"daily_email": False}, headers=teacher
    )
    run()

    assert switched.status_code == 200, switched.text
    assert switched.json()["daily_email"] is False
    assert [email.to for email in mailer.sent] == [LISA]


def test_deactivated_members_get_nothing(
    client: TestClient, mailer: FakeMailer, run, drone
):
    staff, project = drone
    add_deadline(client, staff, project, "Poster due", at(23, 59))
    lisa = client.get(f"/api/projects/{project}", headers=staff).json()["members"][0]
    client.post(f"/api/users/{lisa['id']}/deactivate", headers=staff)

    run()

    assert [email.to for email in mailer.sent] == [TEACHER]


def test_a_failing_address_doesnt_stop_the_others(
    client: TestClient, mailer: FakeMailer, run, drone
):
    staff, project = drone
    add_deadline(client, staff, project, "Poster due", at(23, 59))
    mailer.failing.add(LISA)

    first = run()
    mailer.failing.clear()
    retried = run(at(9))

    assert first == 1
    assert [email.to for email in mailer.sent] == [TEACHER, LISA]
    assert retried == 1


def test_archived_projects_get_nothing(
    client: TestClient, mailer: FakeMailer, run, drone
):
    staff, project = drone
    add_deadline(client, staff, project, "Poster due", at(23, 59))
    client.post(f"/api/projects/{project}/archive", headers=staff)
    add_deadline(client, staff, None, "Final presentation", at(14))

    assert run() == 0


def test_without_a_mailbox_nothing_is_sent(
    client: TestClient, mailer: FakeMailer, run, drone, settings: Settings
):
    staff, project = drone
    add_deadline(client, staff, project, "Poster due", at(23, 59))

    assert run(settings=settings) == 0
    assert mailer.sent == []


def test_the_switch_is_on_by_default(client: TestClient):
    student = ready_to_work(client, "student")

    me = client.get("/api/auth/me", headers=student).json()

    assert me["daily_email"] is True
