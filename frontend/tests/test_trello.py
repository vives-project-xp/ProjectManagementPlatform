from nicegui import ui
from nicegui.testing import User

from pmp_backend.testing import FakeTrello
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


async def test_check_members_updates_the_status(user: User, trello: FakeTrello):
    await ready_to_work(user, "teacher")
    await project_with_the_student(user, "Drone")
    await create_boards_for_all(user)
    await user.should_see("Drone: Created", retries=30)

    await user.open("/projects/1")
    await user.should_see(
        "Student Account (Member): Invited: sign up on Trello with student@pmp.local",
        retries=30,
    )
    # Someone takes the Student off the board in Trello; checking invites again.
    board = trello.board_named("Drone")
    student = next(
        k for k, m in board.members.items() if m.email == "student@pmp.local"
    )
    del board.members[student]
    trello.sign_up("student@pmp.local")
    user.find(marker="check-trello-members").click()

    await user.should_see("Invited Student Account.", retries=30)
    await user.should_see("Student Account (Member): Has access", retries=30)


async def test_check_all_trello_members_shows_a_result_per_project(user: User):
    await ready_to_work(user, "teacher")
    await project_with_the_student(user, "Drone")
    await create_boards_for_all(user)
    await user.should_see("Drone: Created", retries=30)
    user.find(marker="results-done").click()

    user.find(marker="check-all-trello-members").click()
    await user.should_see("Check the members of every Trello board?", retries=30)
    user.find(marker="confirm").click()

    await user.should_see("Drone: Everything was already in order.", retries=30)


async def test_student_sees_how_to_get_access(user: User, trello: FakeTrello):
    await ready_to_work(user, "student")
    email, password = STARTING_ACCOUNTS["superuser"]
    staff, _ = await api.login(email, password)
    await api.change_password(staff, password, "superuser-own-password")
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
    await api.create_trello_boards(staff)

    await user.open("/my-project")
    await user.should_see(marker="trello-sign-up", retries=30)
    link = user.find(marker="trello-sign-up").elements.pop()
    assert isinstance(link, ui.link)
    assert link.text == "Sign up on Trello with student@pmp.local to get access"
    assert link.props["href"] == "https://trello.com/signup"

    trello.sign_up("student@pmp.local")
    await user.open("/my-project")
    await user.should_see(marker="trello-has_access", retries=30)
