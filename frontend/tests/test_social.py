from nicegui import ui
from nicegui.testing import User

from pmp_frontend import api
from tests.conftest import ready_to_work
from tests.test_chat import api_token, drone_with_the_student, navigation_targets

WEDNESDAY_17 = {
    "upload_weekday": 2,
    "upload_time": "17:00",
    "instagram_weekdays": [0, 1, 2, 3, 4],
    "instagram_times": ["12:00", "19:00"],
    "fixed_hashtags": "#VIVEShogeschool #ElektronicaICT",
}


async def test_the_superuser_sets_the_upload_deadline(user: User) -> None:
    await ready_to_work(user, "superuser")
    assert "/social-media" in navigation_targets(user)

    await user.open("/social-media")
    await user.should_see(marker="upload-weekday")
    weekday = user.find(marker="upload-weekday").elements.pop()
    assert isinstance(weekday, ui.select)
    weekday.set_value(2)
    user.find(marker="upload-time").type("17:00")
    user.find(marker="fixed-hashtags").elements.pop().set_value("#VIVES #EOICT")
    user.find(marker="save-social-settings").click()

    await user.should_see("The social media settings were saved.")
    token = await api.login("superuser@pmp.local", "superuser-own-password")
    saved = await api.social_settings(token[0])
    assert (saved["upload_weekday"], saved["upload_time"]) == (2, "17:00")
    assert saved["fixed_hashtags"] == "#VIVES #EOICT"


async def test_a_wrong_setting_shows_why(user: User) -> None:
    await ready_to_work(user, "superuser")
    await user.open("/social-media")
    await user.should_see(marker="fixed-hashtags")
    user.find(marker="fixed-hashtags").elements.pop().set_value("VIVES")
    user.find(marker="save-social-settings").click()

    await user.should_see('"VIVES" is not a hashtag', retries=30)


async def test_a_member_writes_the_weekly_update(user: User) -> None:
    staff = await api_token("superuser")
    await api.set_social_settings(staff, WEDNESDAY_17)
    project = await drone_with_the_student(staff)

    await ready_to_work(user, "student")
    assert "/weekly-update" in navigation_targets(user)
    await user.open("/weekly-update")
    await user.should_see("This Upload week closes on")
    user.find(marker="weekly-update-text").type("We built the frame.")
    user.find(marker="save-weekly-update").click()

    await user.should_see("Last edited by Student Account", retries=30)
    weeks = await api.project_weekly_updates(staff, project)
    assert [week["text"] for week in weeks] == ["We built the frame."]


async def test_before_the_deadline_is_set_members_wait(user: User) -> None:
    staff = await api_token("superuser")
    await drone_with_the_student(staff)

    await ready_to_work(user, "student")
    await user.open("/weekly-update")

    await user.should_see("The Upload deadline hasn't been set yet.")
    await user.should_not_see(marker="save-weekly-update")


async def test_a_student_without_a_project_has_no_weekly_update(user: User) -> None:
    await ready_to_work(user, "student")
    assert "/weekly-update" not in navigation_targets(user)


async def test_staff_read_the_weekly_updates_on_the_project_page(user: User) -> None:
    staff = await api_token("superuser")
    await api.set_social_settings(staff, WEDNESDAY_17)
    project = await drone_with_the_student(staff)
    student, _ = await api.login("student@pmp.local", "student-secret-1")
    await api.change_password(student, "student-secret-1", "student-api-password")
    await api.save_weekly_update(student, "Tested the motors.")

    await ready_to_work(user, "teacher")
    await user.open(f"/projects/{project}")

    await user.should_see(marker="weekly-updates-card")
    await user.should_see("Tested the motors.")
