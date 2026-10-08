import pytest
from nicegui import ui
from nicegui.testing import User

from tests.conftest import change_starting_password, log_in, ready_to_work


async def test_first_login_forces_a_password_change(user: User):
    await log_in(user, "teacher")

    await user.should_see("Choose a new password of your own before you continue.")
    await user.should_not_see("Projects")

    await change_starting_password(user, "teacher", "my-new-password")

    # The Teacher's home page (Projects) loads its data before it shows.
    await user.should_see(marker="navigation", retries=30)
    await user.should_see("Teacher Account")
    await user.should_see("Projects")
    await user.should_see("Members")
    await user.should_not_see("Users")


async def test_forced_change_cannot_be_skipped(user: User):
    await log_in(user, "teacher")
    await user.should_see("Change your password")

    await user.open("/projects")

    await user.should_see("Change your password")


async def test_wrong_password_shows_a_generic_error(user: User):
    await log_in(user, "teacher", password="not-the-password")

    await user.should_see("Incorrect email or password.")


async def test_new_passwords_must_match(user: User):
    await log_in(user, "student")
    await user.should_see("Change your password")
    user.find(marker="current-password").type("student-secret-1")
    user.find(marker="new-password").type("my-new-password")
    user.find(marker="repeat-password").type("something-else")
    user.find(marker="change-password").click()

    await user.should_see("The new passwords do not match.")


async def test_student_only_sees_my_project(user: User):
    await ready_to_work(user, "student")

    await user.should_see("My project")
    await user.should_not_see("Projects")
    await user.should_not_see("Members")
    await user.should_not_see("Users")

    await user.open("/users")

    await user.should_see("You don't have access to this page.")


async def test_log_out_returns_to_login(user: User):
    await ready_to_work(user, "superuser")

    user.find("Log out").click()

    await user.should_see(marker="log-in")
    await user.open("/users")
    await user.should_see(marker="log-in")


async def test_login_page_has_no_test_login_by_default(user: User):
    await user.open("/login")
    await user.should_see(marker="log-in")

    await user.should_not_see("Test login")


@pytest.mark.dev_login
async def test_test_login_logs_in_as_the_chosen_user(user: User):
    await user.open("/login")
    await user.should_see("Test login", retries=30)
    choice = user.find(marker="dev-login-user").elements.pop()
    assert isinstance(choice, ui.select)
    assert list(choice.options.values()) == [
        "Superuser Account (Superuser)",
        "Teacher Account (Teacher)",
        "Student Account (Student)",
    ]

    choice.set_value(
        next(
            key for key, label in choice.options.items() if label.startswith("Teacher")
        )
    )
    user.find(marker="dev-log-in").click()

    # Starting accounts still have their Temporary password.
    await user.should_see("Change your password", retries=30)
