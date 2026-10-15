from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from nicegui import ui
from nicegui.testing import User

from pmp_frontend import api
from tests.conftest import (
    STARTING_ACCOUNTS,
    choose_student,
    create_project,
    ready_to_work,
)

BRUSSELS = ZoneInfo("Europe/Brussels")


def in_days(days: int) -> str:
    return (datetime.now(BRUSSELS).date() + timedelta(days=days)).isoformat()


def fill_deadline(user: User, title: str, date: str) -> None:
    user.find(marker="deadline-title").elements.pop().set_value(title)
    user.find(marker="deadline-date").elements.pop().set_value(date)


async def test_teacher_adds_a_deadline_the_student_sees_it(user: User):
    await ready_to_work(user, "teacher")
    await create_project(user, "Drone", 1, 3)
    await user.open("/projects/1")
    await user.should_see(marker="add-member", retries=30)
    choose_student(user, "Student Account")
    user.find(marker="add-member").click()
    await user.should_see("Members (1 / 1–3)", retries=30)

    user.find(marker="add-deadline").click()
    # Not the text: "New deadline" is also on the Planning screen's button.
    await user.should_see(marker="deadline-title", retries=30)
    fill_deadline(user, "Prototype demo", in_days(0))
    user.find(marker="save-deadline").click()

    await user.should_see("The deadline Prototype demo was added.", retries=30)
    await user.should_see(marker="today-banner", retries=30)
    # The Student sees it on My project.
    email, password = STARTING_ACCOUNTS["student"]
    student_token, _ = await api.login(email, password)
    await api.change_password(student_token, password, "student-own-password")
    assert [d["title"] for d in (await api.my_planning(student_token))["items"]] == [
        "Prototype demo"
    ]


async def test_a_deadline_for_all_projects_shows_on_the_planning_screen(user: User):
    await ready_to_work(user, "teacher")
    await create_project(user, "Drone", 1, 3)

    await user.open("/planning")
    await user.should_see(marker="add-deadline-for-all", retries=30)
    user.find(marker="add-deadline-for-all").click()
    # Not the text: "New deadline" is also on the Planning screen's button.
    await user.should_see(marker="deadline-title", retries=30)
    fill_deadline(user, "Final presentation", in_days(0))
    user.find(marker="save-deadline").click()

    await user.should_see(
        "The deadline Final presentation was added for all Projects.", retries=30
    )
    await user.should_see(marker="today-banner", retries=30)
    banner = user.find(marker="today-banner").elements.pop()
    texts = [
        child.text for child in banner.descendants() if isinstance(child, ui.label)
    ]
    assert "23:59 · Final presentation (All Projects)" in texts
    # And on the Project's page, read-only there.
    await user.open("/projects/1")
    await user.should_see(marker="planning-card", retries=30)
    await user.should_see("Final presentation", retries=30)
    await user.should_not_see(marker="edit-deadline")


async def test_a_student_sees_the_planning_on_my_project(user: User):
    await ready_to_work(user, "student")
    email, password = STARTING_ACCOUNTS["superuser"]
    staff, _ = await api.login(email, password)
    await api.change_password(staff, password, "superuser-own-password")
    owner = (await api.teachers(staff))[0]["id"]
    project = await api.create_project(
        staff,
        {
            "title": "Drone",
            "description": None,
            "product_owner_id": owner,
            "team_size_min": 1,
            "team_size_max": 3,
        },
    )
    # User 3 is the Student starting account.
    await api.add_member(staff, project["id"], 3)
    await api.add_deadline(
        staff,
        project["id"],
        {"title": "Poster due", "due_at": f"{in_days(2)}T23:59:00+01:00"},
    )

    await user.open("/my-project")

    await user.should_see(marker="my-planning", retries=30)
    await user.should_see("Poster due", retries=30)
    await user.should_not_see(marker="add-deadline")


async def test_teacher_sets_a_weekly_meeting_the_student_sees_it(user: User):
    await ready_to_work(user, "student")
    email, password = STARTING_ACCOUNTS["superuser"]
    staff, _ = await api.login(email, password)
    await api.change_password(staff, password, "superuser-own-password")
    owner = (await api.teachers(staff))[0]["id"]
    project = await api.create_project(
        staff,
        {
            "title": "Drone",
            "description": None,
            "product_owner_id": owner,
            "team_size_min": 1,
            "team_size_max": 3,
        },
    )
    # User 3 is the Student starting account.
    await api.add_member(staff, project["id"], 3)
    await api.set_weekly_slot(
        staff,
        project["id"],
        {"weekday": 1, "starts": "10:00", "ends": "10:30", "place": "B2.14"},
    )
    await api.add_meeting(
        staff,
        project["id"],
        {
            "starts_at": f"{in_days(2)}T14:00:00+01:00",
            "ends_at": f"{in_days(2)}T15:00:00+01:00",
            "place": "https://teams.example/demo",
        },
    )

    await user.open("/my-project")

    await user.should_see(marker="weekly-slot", retries=30)
    await user.should_see("Every Tuesday 10:00–10:30 · B2.14", retries=30)
    await user.should_see("https://teams.example/demo", retries=30)
    await user.should_not_see(marker="add-meeting")


async def test_teacher_adds_a_meeting_on_the_project_page(user: User):
    await ready_to_work(user, "teacher")
    await create_project(user, "Drone", 1, 3)
    await user.open("/projects/1")
    await user.should_see(marker="add-meeting", retries=30)

    user.find(marker="add-meeting").click()
    await user.should_see(marker="meeting-date", retries=30)
    user.find(marker="meeting-date").elements.pop().set_value(in_days(1))
    user.find(marker="meeting-starts").elements.pop().set_value("14:00")
    user.find(marker="meeting-ends").elements.pop().set_value("15:00")
    user.find(marker="meeting-place").elements.pop().set_value("B2.14")
    user.find(marker="save-meeting").click()

    await user.should_see("The meeting was added.", retries=30)
    await user.should_see(marker="edit-meeting", retries=30)


async def test_switching_the_daily_email_off(user: User):
    await ready_to_work(user, "student")
    await user.open("/account")
    await user.should_see(marker="daily-email", retries=30)
    switch = user.find(marker="daily-email").elements.pop()
    assert isinstance(switch, ui.switch)
    assert switch.value is True

    switch.set_value(False)

    await user.should_see("No more daily emails.", retries=30)
    email, _ = STARTING_ACCOUNTS["student"]
    token, me = await api.login(email, "student-own-password")
    assert me.daily_email is False


async def test_the_superuser_has_no_daily_email_switch(user: User):
    await ready_to_work(user, "superuser")
    await user.open("/account")
    await user.should_see("My account", retries=30)

    await user.should_not_see(marker="daily-email")
