"""Save buttons are greyed out while the form shows what is saved (#121)."""

from nicegui.testing import User

from pmp_frontend import api
from tests.conftest import create_project, eventually, ready_to_work
from tests.test_chat import api_token, drone_with_the_student
from tests.test_social import WEDNESDAY_17


def enabled(user: User, marker: str) -> bool:
    return user.find(marker=marker).elements.pop().enabled


def field(user: User, marker: str):
    return user.find(marker=marker).elements.pop()


async def test_the_social_settings_save_button(user: User) -> None:
    await ready_to_work(user, "superuser")
    await user.open("/social-media")
    await user.should_see(marker="save-social-settings")
    assert not enabled(user, "save-social-settings")

    hashtags = field(user, "fixed-hashtags")
    hashtags.set_value("#VIVES")
    await eventually(lambda: enabled(user, "save-social-settings"))
    # Back to what is saved: nothing to save.
    hashtags.set_value("#VIVEShogeschool #ElektronicaICT")
    await eventually(lambda: not enabled(user, "save-social-settings"))

    hashtags.set_value("#VIVES")
    user.find(marker="save-social-settings").click()
    await user.should_see("The social media settings were saved.")
    assert not enabled(user, "save-social-settings")


async def test_a_refused_save_keeps_the_button_active(user: User) -> None:
    await ready_to_work(user, "superuser")
    await user.open("/social-media")
    await user.should_see(marker="save-social-settings")

    field(user, "fixed-hashtags").set_value("no-hashtag")
    user.find(marker="save-social-settings").click()

    await user.should_see('"no-hashtag" is not a hashtag', retries=30)
    assert enabled(user, "save-social-settings")


async def test_the_weekly_update_save_button(user: User) -> None:
    staff = await api_token("superuser")
    await api.set_social_settings(staff, WEDNESDAY_17)
    await drone_with_the_student(staff)
    await ready_to_work(user, "student")
    await user.open("/weekly-update")
    await user.should_see(marker="save-weekly-update")
    assert not enabled(user, "save-weekly-update")

    field(user, "weekly-update-text").set_value("We built the frame.")
    await eventually(lambda: enabled(user, "save-weekly-update"))
    user.find(marker="save-weekly-update").click()

    await user.should_see("Last edited by Student Account", retries=30)
    assert not enabled(user, "save-weekly-update")


async def test_the_project_and_repository_save_buttons(user: User) -> None:
    await ready_to_work(user, "teacher")
    await create_project(user, "Drone", 1, 3)
    await user.open("/projects/1")
    await user.should_see(marker="save-project", retries=30)
    assert not enabled(user, "save-project")
    assert not enabled(user, "save-repo-name")

    field(user, "title").set_value("Drone 2")
    await eventually(lambda: enabled(user, "save-project"))
    user.find(marker="save-project").click()
    await user.should_see("The changes were saved.", retries=30)
    assert not enabled(user, "save-project")

    field(user, "repo-name").set_value("Drone2026")
    await eventually(lambda: enabled(user, "save-repo-name"))
    user.find(marker="save-repo-name").click()
    await user.should_see("The repository will be called Drone2026.", retries=30)
    assert not enabled(user, "save-repo-name")


async def test_the_user_save_button(user: User) -> None:
    await ready_to_work(user, "superuser")
    # User 2 is the Teacher starting account.
    await user.open("/users/2")
    await user.should_see(marker="save-user")
    assert not enabled(user, "save-user")

    field(user, "last-name").set_value("Janssens")
    await eventually(lambda: enabled(user, "save-user"))
    user.find(marker="save-user").click()

    await user.should_see("The changes were saved.")
    assert not enabled(user, "save-user")
