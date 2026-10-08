from datetime import date, timedelta

from nicegui import ui
from nicegui.testing import User

from tests.conftest import (
    change_starting_password,
    create_project,
    log_in,
    ready_to_work,
)


async def open_for_choice(user: User, project_id: int, title: str) -> None:
    await user.open(f"/projects/{project_id}")
    await user.should_see(marker="open-for-choice", retries=30)
    switch = user.find(marker="open-for-choice").elements.pop()
    assert isinstance(switch, ui.switch)
    switch.set_value(True)
    await user.should_see(f"{title} is open for choice.")


async def open_round(user: User) -> None:
    await user.open("/top3")
    await user.should_see("No Top 3 round yet.", retries=30)
    tomorrow = date.today() + timedelta(days=1)
    user.find(marker="deadline-date").elements.pop().set_value(tomorrow.isoformat())
    user.find(marker="set-deadline").click()
    await user.should_see("Open until", retries=30)


async def log_in_as_student(user: User) -> None:
    user.find("Log out").click()
    await user.should_see("Log in")
    await log_in(user, "student")
    await change_starting_password(user, "student", "student-own-password")


async def test_student_submits_their_top3(user: User):
    await ready_to_work(user, "teacher")
    titles = ["Drone", "Robot", "Smart Greenhouse"]
    for project_id, title in enumerate(titles, start=1):
        await create_project(user, title, 1, 3)
        await open_for_choice(user, project_id, title)
    await open_round(user)
    await log_in_as_student(user)

    await user.should_see(marker="submit-top3", retries=30)
    await user.should_see("Product Owner: Teacher Account")
    # Robot 1st, Smart Greenhouse 2nd, Drone 3rd.
    for place, project_id in enumerate([2, 3, 1], start=1):
        user.find(marker=f"choice-{place}").elements.pop().set_value(project_id)
    user.find(marker="submit-top3").click()
    await user.should_see("Submit this top 3?", retries=10)
    user.find(marker="confirm").click()

    await user.should_see("1st choice: Robot", retries=30)
    await user.should_see("2nd choice: Smart Greenhouse")
    await user.should_see("3rd choice: Drone")
    await user.should_not_see(marker="submit-top3")


async def test_choosing_opens_later_before_a_round(user: User):
    await ready_to_work(user, "student")

    await user.open("/my-project")

    await user.should_see("Choosing opens later.", retries=30)


async def test_the_same_project_twice_is_refused(user: User):
    await ready_to_work(user, "teacher")
    for project_id, title in enumerate(["Drone", "Robot"], start=1):
        await create_project(user, title, 1, 3)
        await open_for_choice(user, project_id, title)
    await open_round(user)
    await log_in_as_student(user)

    await user.should_see(marker="submit-top3", retries=30)
    user.find(marker="choice-1").elements.pop().set_value(1)
    user.find(marker="choice-2").elements.pop().set_value(1)
    user.find(marker="submit-top3").click()
    await user.should_see("Submit this top 3?", retries=10)
    user.find(marker="confirm").click()

    await user.should_see("Choose each Project only once.")
