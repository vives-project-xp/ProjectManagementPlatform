from nicegui import ui
from nicegui.testing import User

from tests.conftest import (
    choose_student,
    create_project,
    eventually,
    ready_to_work,
)


def student_rows(user: User) -> list[tuple[str, str]]:
    table = user.find(marker="students").elements.pop()
    assert isinstance(table, ui.table)
    return [(row["name"], row["project"]) for row in table.rows]


async def test_teacher_sees_students_and_filters_on_no_project(user: User):
    await ready_to_work(user, "teacher")

    await user.open("/members")
    await user.should_see(marker="students")
    await eventually(
        lambda: student_rows(user) == [("Student Account", "No Project yet")]
    )

    await create_project(user, "Drone", 1, 3)
    await user.open("/projects/1")
    await user.should_see(marker="add-member")
    choose_student(user, "Student Account")
    user.find(marker="add-member").click()
    await user.should_see("Members (1 / 1–3)")

    await user.open("/members")
    await user.should_see(marker="students")
    await eventually(lambda: student_rows(user) == [("Student Account", "Drone")])
    user.find(marker="without-project").elements.pop().set_value(True)
    await eventually(lambda: student_rows(user) == [])


async def test_student_has_no_members_screen(user: User):
    await ready_to_work(user, "student")

    await user.open("/members")

    await user.should_see("You don't have access to this page.")
