from nicegui.testing import User

from pmp_backend.testing import FakeGitHub
from tests.conftest import ready_to_work


async def check_and_save(user: User, username: str) -> None:
    user.find(marker="github-username").elements.pop().set_value(username)
    user.find(marker="check-github").click()


async def test_student_saves_their_username_after_confirming(
    user: User, github: FakeGitHub
):
    github.add_account("Lisa-P", name="Lisa Peeters")
    await ready_to_work(user, "student")
    await user.open("/my-project")
    await user.should_see(marker="github-card", retries=30)
    await user.should_see("No GitHub username saved yet.")

    await check_and_save(user, "lisa-p")
    # The account's name and picture, before anything is saved.
    await user.should_see("Lisa Peeters", retries=30)
    user.find(marker="save-github").click()

    await user.should_see("Saved: Lisa-P", retries=30)


async def test_an_unknown_account_is_shown(user: User):
    await ready_to_work(user, "teacher")
    await user.open("/account")
    await user.should_see(marker="github-card", retries=30)

    await check_and_save(user, "nobody-here")

    await user.should_see("No GitHub account is called nobody-here.")


async def test_my_account_has_password_and_github(user: User, github: FakeGitHub):
    github.add_account("Teach-Er")
    await ready_to_work(user, "teacher")

    await user.open("/account")
    await user.should_see("Change your password", retries=30)
    await check_and_save(user, "teach-er")
    await user.should_see(marker="save-github", retries=30)
    user.find(marker="save-github").click()
    await user.should_see("Saved: Teach-Er", retries=30)

    user.find(marker="remove-github").click()
    await user.should_see("No GitHub username saved yet.", retries=30)


async def test_the_old_change_password_link_still_works(user: User):
    await ready_to_work(user, "teacher")

    await user.open("/change-password")

    await user.should_see("My account", retries=30)


async def test_superuser_sets_a_users_username(user: User, github: FakeGitHub):
    github.add_account("Teach-Er", name="Ann Janssens")
    await ready_to_work(user, "superuser")

    # User 2 is the Teacher starting account.
    await user.open("/users/2")
    await user.should_see(marker="github-card", retries=30)
    await check_and_save(user, "Teach-Er")
    await user.should_see("Ann Janssens", retries=30)
    user.find(marker="save-github").click()

    await user.should_see("Saved: Teach-Er", retries=30)
