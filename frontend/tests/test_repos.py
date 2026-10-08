from nicegui import ui
from nicegui.testing import User

from pmp_backend.testing import FakeGitHub
from tests.conftest import choose_student, create_project, ready_to_work


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
