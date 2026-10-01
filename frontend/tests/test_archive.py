from nicegui import ui
from nicegui.testing import User

from tests.conftest import (
    choose_student,
    create_project,
    eventually,
    project_titles,
    ready_to_work,
)


async def test_teacher_archives_and_restores_a_project(user: User):
    await ready_to_work(user, "teacher")
    await create_project(user, "Drone", 1, 3)
    await user.open("/projects/1")
    await user.should_see(marker="add-member")
    choose_student(user, "Student Account")
    user.find(marker="add-member").click()
    await user.should_see("Members (1 / 1–3)")

    user.find(marker="change-status").click()
    await user.should_see("Archive Drone?", retries=10)
    user.find(marker="confirm").click()

    # Read-only, with the former Member listed as a Maker.
    await user.should_see("Status: Archived", retries=30)
    await user.should_see("Made by")
    await user.should_see("Student Account — Electronics-ICT, year 1")
    await user.should_not_see(marker="save-project")
    await user.should_not_see(marker="add-member")

    await user.open("/projects")
    await user.should_see(marker="projects")
    await eventually(lambda: project_titles(user) == [])
    status_filter = user.find(marker="status-filter").elements.pop()
    assert isinstance(status_filter, ui.toggle)
    status_filter.set_value("archived")
    await eventually(lambda: project_titles(user) == ["Drone"])

    await user.open("/projects/1")
    user.find(marker="change-status").click()
    await user.should_see("Restore Drone?", retries=10)
    user.find(marker="confirm").click()

    await user.should_see("Status: Active", retries=30)
    await user.should_see("Members (0 / 1–3)")
    await user.should_see("Made by")
