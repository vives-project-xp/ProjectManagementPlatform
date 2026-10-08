from nicegui import ui
from nicegui.testing import User

from tests.conftest import (
    JPG,
    change_starting_password,
    choose_student,
    create_project,
    log_in,
    ready_to_work,
    upload_photo,
)


async def test_student_without_project_sees_not_assigned_message(user: User):
    await ready_to_work(user, "student")

    await user.open("/my-project")
    await user.should_see("You haven't been assigned to a project yet.", retries=30)


async def test_student_sees_own_project(user: User):
    await ready_to_work(user, "teacher")
    await create_project(user, "Drone", 1, 3)
    await user.open("/projects/1")
    await user.should_see(marker="add-member")
    choose_student(user, "Student Account")
    user.find(marker="add-member").click()
    await user.should_see("Members (1 / 1–3)")
    user.find("Log out").click()
    await user.should_see("Log in")

    await log_in(user, "student")
    await change_starting_password(user, "student", "student-own-password")

    await user.should_see("Drone", retries=30)
    await user.should_see("Product Owner: Teacher Account")
    await user.should_see("You are the only Member so far.")
    await user.should_see(marker="photo-placeholder")


async def test_student_sees_their_projects_photo(user: User):
    await ready_to_work(user, "teacher")
    await create_project(user, "Drone", 1, 3)
    await user.open("/projects/1")
    await user.should_see(marker="add-member")
    choose_student(user, "Student Account")
    user.find(marker="add-member").click()
    await user.should_see("Members (1 / 1–3)")
    await upload_photo(user)
    await user.should_see(marker="project-photo", retries=30)
    user.find("Log out").click()
    await user.should_see("Log in")

    await log_in(user, "student")
    await change_starting_password(user, "student", "student-own-password")

    await user.should_see(marker="project-photo", retries=30)
    photo = user.find(marker="project-photo").elements.pop()
    assert isinstance(photo, ui.image)
    assert photo.source == "/photos/1?v=1"
    response = await user.http_client.get(photo.source)
    assert response.status_code == 200
    assert response.content == JPG


async def test_student_is_refused_other_screens(user: User):
    await ready_to_work(user, "student")

    for path in ["/projects", "/projects/1", "/members", "/users"]:
        await user.open(path)
        await user.should_see("You don't have access to this page.", retries=30)
