from nicegui import ui
from nicegui.testing import User

from tests.conftest import eventually, ready_to_work


def table_emails(user: User) -> list[str]:
    table = user.find(marker="users").elements.pop()
    assert isinstance(table, ui.table)
    return [row["email"] for row in table.rows]


async def test_superuser_creates_a_student(user: User):
    await ready_to_work(user, "superuser")
    await user.open("/users")
    await user.should_see(marker="users")
    assert len(table_emails(user)) == 3

    user.find(marker="new-user").click()
    user.find(marker="role").elements.pop().set_value("student")
    user.find(marker="first-name").type("Lisa")
    user.find(marker="last-name").type("Peeters")
    user.find(marker="new-email").type("Lisa.Peeters@student.vives.be")
    user.find(marker="programme").elements.pop().set_value("Electronics-ICT")
    user.find(marker="year").elements.pop().set_value("International")
    user.find(marker="temporary-password").type("welcome-lisa")
    user.find(marker="create-user").click()

    await user.should_see("Lisa Peeters was created.")
    await eventually(lambda: "lisa.peeters@student.vives.be" in table_emails(user))


async def test_duplicate_email_is_shown_in_the_dialog(user: User):
    await ready_to_work(user, "superuser")
    await user.open("/users")

    user.find(marker="new-user").click()
    user.find(marker="first-name").type("Copy")
    user.find(marker="last-name").type("Teacher")
    user.find(marker="new-email").type("TEACHER@pmp.local")
    user.find(marker="temporary-password").type("welcome-copy")
    user.find(marker="create-user").click()

    await user.should_see("The email address teacher@pmp.local is already in use.")


async def test_invalid_input_gets_a_readable_message(user: User):
    await ready_to_work(user, "superuser")
    await user.open("/users")

    user.find(marker="new-user").click()
    user.find(marker="first-name").type("Ann")
    user.find(marker="last-name").type("Janssens")
    user.find(marker="new-email").type("ann.janssens@vives.be")
    user.find(marker="temporary-password").type("short")
    user.find(marker="create-user").click()

    await user.should_see(
        "Temporary password: String should have at least 8 characters."
    )


async def test_superuser_edits_and_deactivates_a_user(user: User):
    await ready_to_work(user, "superuser")

    # User 2 is the Teacher starting account.
    await user.open("/users/2")
    await user.should_see(marker="save-user")
    user.find(marker="last-name").elements.pop().set_value("Janssens")
    user.find(marker="save-user").click()
    await user.should_see("The changes were saved.")

    user.find(marker="toggle-active").click()
    await user.should_see("The User was deactivated.")
    await user.should_see("Status: Deactivated")

    await user.open("/users")
    await user.should_see(marker="users")
    user.find(marker="status-filter").elements.pop().set_value("Deactivated")
    await eventually(lambda: table_emails(user) == ["teacher@pmp.local"])


async def test_teacher_has_no_users_screen(user: User):
    await ready_to_work(user, "teacher")

    await user.should_not_see("Users")
    await user.open("/users")

    await user.should_see("You don't have access to this page.")
