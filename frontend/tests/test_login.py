from nicegui.testing import User

from tests.conftest import STARTING_ACCOUNTS


async def log_in(user: User, role: str, password: str | None = None) -> None:
    email, starting_password = STARTING_ACCOUNTS[role]
    await user.open("/login")
    user.find(marker="email").type(email)
    user.find(marker="password").type(password or starting_password)
    user.find(marker="log-in").click()


async def change_starting_password(user: User, role: str, new_password: str) -> None:
    _, starting_password = STARTING_ACCOUNTS[role]
    await user.should_see("Change your password")
    user.find(marker="current-password").type(starting_password)
    user.find(marker="new-password").type(new_password)
    user.find(marker="repeat-password").type(new_password)
    user.find(marker="change-password").click()


async def test_first_login_forces_a_password_change(user: User):
    await log_in(user, "teacher")

    await user.should_see("Choose a new password of your own before you continue.")
    await user.should_not_see("Projects")

    await change_starting_password(user, "teacher", "my-new-password")

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
    await log_in(user, "student")
    await change_starting_password(user, "student", "my-new-password")

    await user.should_see("My project")
    await user.should_not_see("Projects")
    await user.should_not_see("Members")
    await user.should_not_see("Users")

    await user.open("/users")

    await user.should_see("You don't have access to this page.")


async def test_log_out_returns_to_login(user: User):
    await log_in(user, "superuser")
    await change_starting_password(user, "superuser", "my-new-password")
    await user.should_see("Users")

    user.find("Log out").click()

    await user.should_see(marker="log-in")
    await user.open("/users")
    await user.should_see(marker="log-in")
