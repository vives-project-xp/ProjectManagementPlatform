from nicegui import ui
from nicegui.testing import User

from tests.conftest import ready_to_work


def project_titles(user: User) -> list[str]:
    table = user.find(marker="projects").elements.pop()
    assert isinstance(table, ui.table)
    return [row["title"] for row in table.rows]


def fill_project_form(user: User, title: str, minimum: int, maximum: int) -> None:
    title_input = user.find(marker="title").elements.pop()
    title_input.set_value(title)
    owner = user.find(marker="product-owner").elements.pop()
    assert isinstance(owner, ui.select)
    owner.set_value(
        next(key for key, name in owner.options.items() if name == "Teacher Account")
    )
    user.find(marker="team-size-min").elements.pop().set_value(minimum)
    user.find(marker="team-size-max").elements.pop().set_value(maximum)


async def create_project(user: User, title: str) -> None:
    await user.open("/projects")
    await user.should_see(marker="projects")
    user.find(marker="new-project").click()
    fill_project_form(user, title, 4, 6)
    user.find(marker="create-project").click()
    await user.should_see(f"Project {title} was created.")


async def test_teacher_creates_a_project(user: User):
    await ready_to_work(user, "teacher")

    await create_project(user, "Smart Greenhouse")

    assert project_titles(user) == ["Smart Greenhouse"]


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
    assert project_titles(user) == ["Greenhouse 2.0"]


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
