from datetime import date, timedelta

from nicegui import ui
from nicegui.testing import User

from pmp_frontend import api
from pmp_frontend.top3_page import deadline_from
from tests.conftest import STARTING_ACCOUNTS, eventually, ready_to_work


async def staff_token() -> str:
    """The Superuser, through the API, past the password change."""
    email, password = STARTING_ACCOUNTS["superuser"]
    token, _ = await api.login(email, password)
    await api.change_password(token, password, "superuser-own-password")
    return token


async def student_submits(project_ids: list[int]) -> None:
    email, password = STARTING_ACCOUNTS["student"]
    token, _ = await api.login(email, password)
    await api.change_password(token, password, "student-own-password")
    await api.submit_top3(token, project_ids)


async def open_round_with(titles: list[str]) -> list[int]:
    """Projects open for choice and an open round, set up through the API."""
    token = await staff_token()
    teachers = await api.teachers(token)
    owner = next(t["id"] for t in teachers if t["name"] == "Teacher Account")
    ids = []
    for title in titles:
        project = await api.create_project(
            token,
            {
                "title": title,
                "description": None,
                "product_owner_id": owner,
                "team_size_min": 1,
                "team_size_max": 3,
            },
        )
        await api.set_open_for_choice(token, project["id"], True)
        ids.append(project["id"])
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    await api.set_top3_deadline(token, deadline_from(tomorrow, "23:59"))
    return ids


async def test_teacher_sees_the_top3s_and_resets_one(user: User):
    drone, robot, greenhouse = await open_round_with(
        ["Drone", "Robot", "Smart Greenhouse"]
    )
    await student_submits([robot, greenhouse, drone])
    await ready_to_work(user, "teacher")

    await user.open("/top3")
    await user.should_see("1st choice: Robot", retries=30)
    await user.should_see("2nd choice: Smart Greenhouse")
    await user.should_see("3rd choice: Drone")
    summary = user.find(marker="top3-summary").elements.pop()
    assert isinstance(summary, ui.table)
    assert [(r["title"], r["first"]) for r in summary.rows] == [
        ("Drone", 0),
        ("Robot", 1),
        ("Smart Greenhouse", 0),
    ]

    user.find(marker="reset-top3-3").click()
    await user.should_see("Reset the top 3 of Student Account?", retries=10)
    user.find(marker="confirm").click()

    await user.should_see("Hasn't chosen yet.", retries=30)
    await eventually(lambda: summary.rows[1]["first"] == 0)


async def test_hasnt_chosen_yet_filter(user: User):
    drone, robot, _ = await open_round_with(["Drone", "Robot", "Smart Greenhouse"])
    await student_submits([robot, drone, 3])
    await ready_to_work(user, "teacher")
    await user.open("/top3")
    await user.should_see("1st choice: Robot", retries=30)

    user.find(marker="without-top3").elements.pop().set_value(True)

    await user.should_see("No Students match these filters.", retries=30)
