from nicegui import ui
from nicegui.testing import User

from pmp_backend.testing import FakeTrello
from tests.conftest import choose_student, create_project, ready_to_work


async def project_with_the_student(user: User, title: str) -> None:
    await create_project(user, title, 1, 3)
    await user.open("/projects/1")
    await user.should_see(marker="add-member", retries=30)
    choose_student(user, "Student Account")
    user.find(marker="add-member").click()
    await user.should_see("Members (1 / 1–3)", retries=30)


async def create_boards_for_all(user: User) -> None:
    await user.open("/projects")
    await user.should_see(marker="create-trello-boards", retries=30)
    user.find(marker="create-trello-boards").click()
    await user.should_see("Create Trello boards for 1 Project?", retries=30)
    user.find(marker="confirm").click()


async def test_teacher_creates_trello_boards_for_all_projects(
    user: User, trello: FakeTrello
):
    await ready_to_work(user, "teacher")
    await project_with_the_student(user, "Drone")

    await create_boards_for_all(user)

    await user.should_see("Drone: Created", retries=30)
    board = trello.board_named("Drone")
    assert board.lists == ["Backlog", "To do", "Doing", "Review", "Done"]
    await user.open("/projects/1")
    await user.should_see(marker="trello-link", retries=30)
    link = user.find(marker="trello-link").elements.pop()
    assert isinstance(link, ui.link)
    assert link.props["href"] == board.url


async def test_a_failure_is_reported(user: User, trello: FakeTrello):
    trello.refused_names.add("Drone")
    await ready_to_work(user, "teacher")
    await project_with_the_student(user, "Drone")

    await create_boards_for_all(user)

    await user.should_see(
        "Drone: Failed. Trello refused: the board limit was reached", retries=30
    )
