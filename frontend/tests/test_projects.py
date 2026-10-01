from nicegui.testing import User

from tests.conftest import (
    create_project,
    eventually,
    fill_project_form,
    project_titles,
    ready_to_work,
)


async def test_teacher_creates_a_project(user: User):
    await ready_to_work(user, "teacher")

    await create_project(user, "Smart Greenhouse")

    await eventually(lambda: project_titles(user) == ["Smart Greenhouse"])


async def test_teacher_edits_a_project_on_its_details_page(user: User):
    await ready_to_work(user, "teacher")
    await create_project(user, "Smart Greenhouse")

    await user.open("/projects/1")
    await user.should_see(marker="save-project")
    fill_project_form(user, "Greenhouse 2.0", 3, 5)
    user.find(marker="save-project").click()

    await user.should_see("The changes were saved.")
    await user.open("/projects")
    await user.should_see(marker="projects")
    await eventually(lambda: project_titles(user) == ["Greenhouse 2.0"])


async def test_duplicate_title_is_shown_in_the_dialog(user: User):
    await ready_to_work(user, "teacher")
    await create_project(user, "Smart Greenhouse")

    user.find(marker="new-project").click()
    fill_project_form(user, "smart greenhouse", 4, 6)
    user.find(marker="create-project").click()

    await user.should_see("A Project called Smart Greenhouse already exists")


async def test_student_has_no_projects_screen(user: User):
    await ready_to_work(user, "student")

    await user.open("/projects")
    await user.should_see("You don't have access to this page.")
    await user.open("/projects/1")
    await user.should_see("You don't have access to this page.")
