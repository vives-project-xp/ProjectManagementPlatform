from datetime import date, timedelta

from nicegui import ui
from nicegui.testing import User

from tests.conftest import create_project, ready_to_work


def tomorrow() -> date:
    return date.today() + timedelta(days=1)


def choose_deadline(user: User, day: date, time: str = "23:59") -> None:
    user.find(marker="deadline-date").elements.pop().set_value(day.isoformat())
    user.find(marker="deadline-time").elements.pop().set_value(time)


async def test_teacher_opens_closes_and_starts_a_new_round(user: User):
    await ready_to_work(user, "teacher")
    await user.open("/top3")
    await user.should_see("No Top 3 round yet.", retries=30)

    choose_deadline(user, tomorrow())
    user.find(marker="set-deadline").click()
    await user.should_see(f"Open until {tomorrow():%d/%m/%Y} 23:59")

    user.find(marker="close-round").click()
    await user.should_see("Close the Top 3 round now?", retries=10)
    user.find(marker="confirm").click()
    await user.should_see("Closed since", retries=30)

    later = tomorrow() + timedelta(days=6)
    choose_deadline(user, later, "12:00")
    user.find(marker="new-round").click()
    await user.should_see("Start a new Top 3 round?", retries=10)
    user.find(marker="confirm").click()
    await user.should_see(f"Open until {later:%d/%m/%Y} 12:00", retries=30)


async def test_a_deadline_in_the_past_is_refused(user: User):
    await ready_to_work(user, "superuser")
    await user.open("/top3")
    await user.should_see("No Top 3 round yet.", retries=30)

    choose_deadline(user, date.today() - timedelta(days=1))
    user.find(marker="set-deadline").click()

    await user.should_see("The deadline must be in the future.")


async def test_teacher_marks_a_project_open_for_choice(user: User):
    await ready_to_work(user, "teacher")
    await create_project(user, "Drone", 1, 3)
    await user.open("/projects/1")
    await user.should_see(marker="open-for-choice", retries=30)

    switch = user.find(marker="open-for-choice").elements.pop()
    assert isinstance(switch, ui.switch)
    switch.set_value(True)
    await user.should_see("Drone is open for choice.")

    await user.open("/projects")
    await user.should_see(marker="projects", retries=30)
    table = user.find(marker="projects").elements.pop()
    assert isinstance(table, ui.table)
    assert table.rows[0]["choice"] == "Yes"


async def test_students_have_no_top3_screen(user: User):
    await ready_to_work(user, "student")

    await user.open("/top3")

    await user.should_see("You don't have access to this page.", retries=30)
