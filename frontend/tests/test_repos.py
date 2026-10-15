from nicegui import ui
from nicegui.testing import User

from pmp_backend.testing import FakeGitHub
from pmp_frontend import api
from tests.conftest import (
    STARTING_ACCOUNTS,
    choose_student,
    create_project,
    ready_to_work,
)


async def project_with_the_student(user: User, title: str) -> None:
    await create_project(user, title, 1, 3)
    await user.open("/projects/1")
    await user.should_see(marker="add-member", retries=30)
    choose_student(user, "Student Account")
    user.find(marker="add-member").click()
    await user.should_see("Members (1 / 1–3)", retries=30)


async def test_teacher_creates_repos_for_all_projects(user: User, github: FakeGitHub):
    await ready_to_work(user, "teacher")
    await project_with_the_student(user, "Drone")
    await user.open("/projects")
    await user.should_see(marker="create-repos", retries=30)

    user.find(marker="create-repos").click()
    await user.should_see("Create repositories for 1 Project in TestOrg?", retries=30)
    user.find(marker="confirm").click()

    await user.should_see("Drone: Created", retries=30)
    assert "drone" in github.repos
    await user.open("/projects/1")
    await user.should_see(marker="repo-link", retries=30)
    link = user.find(marker="repo-link").elements.pop()
    assert isinstance(link, ui.link)
    assert link.props["href"] == "https://github.com/TestOrg/Drone"


async def test_a_taken_name_is_reported(user: User, github: FakeGitHub):
    github.add_repo("TestOrg", "Drone")
    await ready_to_work(user, "teacher")
    await project_with_the_student(user, "Drone")
    await user.open("/projects")
    await user.should_see(marker="create-repos", retries=30)

    user.find(marker="create-repos").click()
    await user.should_see("Create repositories for 1 Project in TestOrg?", retries=30)
    user.find(marker="confirm").click()

    await user.should_see(
        "Drone: Failed. A repository called Drone already exists in TestOrg. "
        "Choose another Repository name.",
        retries=30,
    )


async def test_teacher_chooses_the_repository_name(user: User):
    await ready_to_work(user, "teacher")
    await create_project(user, "Smart Greenhouse", 1, 3)
    await user.open("/projects/1")
    await user.should_see(marker="repo-name", retries=30)
    name = user.find(marker="repo-name").elements.pop()
    assert isinstance(name, ui.input)
    assert name.value == "SmartGreenhouse"

    name.set_value("Greenhouse2026")
    user.find(marker="save-repo-name").click()

    await user.should_see("The repository will be called Greenhouse2026.", retries=30)


async def test_check_members_updates_the_status(user: User, github: FakeGitHub):
    await ready_to_work(user, "teacher")
    await project_with_the_student(user, "Drone")
    await user.open("/projects")
    await user.should_see(marker="create-repos", retries=30)
    user.find(marker="create-repos").click()
    await user.should_see("Create repositories for 1 Project in TestOrg?", retries=30)
    user.find(marker="confirm").click()
    await user.should_see("Drone: Created", retries=30)

    await user.open("/projects/1")
    await user.should_see(
        "Student Account (Member): No GitHub username yet", retries=30
    )
    # The Student adds a username; checking invites them.
    github.add_account("Stu-D")
    email, password = STARTING_ACCOUNTS["student"]
    student_token, _ = await api.login(email, password)
    await api.change_password(student_token, password, "student-own-password")
    await api.set_my_github_username(student_token, "Stu-D")
    user.find(marker="check-members").click()

    await user.should_see("Invited Stu-D.", retries=30)
    await user.should_see(
        "Student Account (Member): Invited, not accepted yet", retries=30
    )
    github.accept("Drone", "Stu-D")
    await user.open("/projects/1")
    await user.should_see("Student Account (Member): Has access", retries=30)


async def test_check_all_members_shows_a_result_per_project(
    user: User, github: FakeGitHub
):
    await ready_to_work(user, "teacher")
    await project_with_the_student(user, "Drone")
    await user.open("/projects")
    await user.should_see(marker="create-repos", retries=30)
    user.find(marker="create-repos").click()
    await user.should_see("Create repositories for 1 Project in TestOrg?", retries=30)
    user.find(marker="confirm").click()
    await user.should_see("Drone: Created", retries=30)
    user.find(marker="results-done").click()

    user.find(marker="check-all-members").click()
    await user.should_see("Check the members of every repository?", retries=30)
    user.find(marker="confirm").click()

    await user.should_see("Drone: Everything was already in order.", retries=30)


async def staff_token() -> str:
    email, password = STARTING_ACCOUNTS["superuser"]
    token, _ = await api.login(email, password)
    await api.change_password(token, password, "superuser-own-password")
    return token


async def test_student_sees_how_to_get_access(user: User, github: FakeGitHub):
    github.add_account("Stu-D")
    await ready_to_work(user, "student")
    staff = await staff_token()
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
    await api.create_repos(staff)

    await user.open("/my-project")
    await user.should_see("Add your GitHub username above to get access.", retries=30)

    await api.set_github_username(staff, 3, "Stu-D")
    await api.check_members(staff, project["id"])
    await user.open("/my-project")
    await user.should_see(marker="accept-invitation", retries=30)
    link = user.find(marker="accept-invitation").elements.pop()
    assert isinstance(link, ui.link)
    assert link.props["href"] == "https://github.com/TestOrg/Drone/invitations"

    github.accept("Drone", "Stu-D")
    await user.open("/my-project")
    await user.should_see("You have access.", retries=30)
