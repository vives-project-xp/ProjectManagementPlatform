from nicegui import ui
from nicegui.testing import User

from tests.conftest import create_project, eventually, ready_to_work


def projects_table_members(user: User) -> dict[str, tuple[str, bool]]:
    table = user.find(marker="projects").elements.pop()
    assert isinstance(table, ui.table)
    return {row["title"]: (row["members"], row["understaffed"]) for row in table.rows}


def choose_student(user: User, name: str) -> None:
    choice = user.find(marker="student-choice").elements.pop()
    assert isinstance(choice, ui.select)
    choice.set_value(
        next(key for key, label in choice.options.items() if label.startswith(name))
    )


async def test_teacher_adds_and_moves_a_member(user: User):
    await ready_to_work(user, "teacher")
    await create_project(user, "Drone", 1, 3)
    await create_project(user, "Smart Greenhouse", 2, 4)
    await eventually(lambda: projects_table_members(user)["Drone"] == ("0 / 1–3", True))

    # Add the Student to Drone (Project 1).
    await user.open("/projects/1")
    await user.should_see(marker="add-member")
    choose_student(user, "Student Account")
    user.find(marker="add-member").click()
    await user.should_see("The Member was added.")
    await user.should_see("Members (1 / 1–3)")

    # Adding them to Smart Greenhouse (Project 2) asks to move them.
    await user.open("/projects/2")
    await user.should_see(marker="add-member")
    choose_student(user, "Student Account")
    user.find(marker="add-member").click()
    await user.should_see(
        "Student Account is a Member of Drone. "
        "Move Student Account to Smart Greenhouse?"
    )
    user.find(marker="confirm").click()
    await user.should_see("Members (1 / 2–4)")

    await user.open("/projects")
    await user.should_see(marker="projects")
    await eventually(
        lambda: (
            projects_table_members(user)
            == {"Drone": ("0 / 1–3", True), "Smart Greenhouse": ("1 / 2–4", True)}
        )
    )


async def test_teacher_removes_a_member_after_confirming(user: User):
    await ready_to_work(user, "teacher")
    await create_project(user, "Drone", 1, 3)
    await user.open("/projects/1")
    await user.should_see(marker="add-member")
    choose_student(user, "Student Account")
    user.find(marker="add-member").click()
    await user.should_see("Members (1 / 1–3)")

    user.find(marker="remove-member").click()
    await user.should_see("Remove Student Account from Drone?")
    user.find(marker="confirm").click()

    await user.should_see("Student Account was removed.")
    await user.should_see("No Members yet.")
