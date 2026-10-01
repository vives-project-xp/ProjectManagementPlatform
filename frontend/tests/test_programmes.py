from nicegui import ui
from nicegui.testing import User

from tests.conftest import eventually, ready_to_work


def listed_programmes(user: User) -> list[str]:
    rows = user.find(marker="programmes").elements.pop()
    return [
        label.text
        for label in rows.descendants()
        if isinstance(label, ui.label) and not isinstance(label, ui.button)
    ]


async def open_programmes(user: User) -> None:
    await ready_to_work(user, "superuser")
    await user.open("/programmes")
    await user.should_see(marker="programmes", retries=30)
    await eventually(lambda: listed_programmes(user) == ["Electronics-ICT"])


async def test_superuser_adds_renames_and_removes_a_programme(user: User):
    await open_programmes(user)

    user.find(marker="new-programme").type("Chemistry")
    user.find(marker="add-programme").click()
    await user.should_see("Programme Chemistry was added.")
    await eventually(
        lambda: listed_programmes(user) == ["Chemistry", "Electronics-ICT"]
    )

    user.find(marker="rename-programme-2").click()
    user.find(marker="programme-name").clear().type("Biochemistry")
    user.find(marker="save-programme").click()
    await user.should_see("Chemistry was renamed to Biochemistry.")
    await eventually(
        lambda: listed_programmes(user) == ["Biochemistry", "Electronics-ICT"]
    )

    user.find(marker="remove-programme-2").click()
    await user.should_see("Remove the Programme Biochemistry?", retries=10)
    user.find(marker="confirm").click()
    await user.should_see("Programme Biochemistry was removed.")
    await eventually(lambda: listed_programmes(user) == ["Electronics-ICT"])


async def test_removing_a_programme_in_use_shows_why(user: User):
    await open_programmes(user)

    user.find(marker="remove-programme-1").click()
    await user.should_see("Remove the Programme Electronics-ICT?", retries=10)
    user.find(marker="confirm").click()

    await user.should_see(
        "1 User still has the Programme Electronics-ICT. Change their Programme first."
    )
    assert listed_programmes(user) == ["Electronics-ICT"]


async def test_a_new_programme_can_be_picked_for_a_student(user: User):
    await open_programmes(user)
    user.find(marker="new-programme").type("Chemistry")
    user.find(marker="add-programme").click()
    await user.should_see("Programme Chemistry was added.")

    await user.open("/users")
    await user.should_see(marker="new-user", retries=30)
    user.find(marker="new-user").click()
    user.find(marker="role").elements.pop().set_value("student")
    programme = user.find(marker="programme").elements.pop()

    assert isinstance(programme, ui.select)
    assert "Chemistry" in programme.options


async def test_teachers_have_no_programmes_screen(user: User):
    await ready_to_work(user, "teacher")

    await user.open("/programmes")

    await user.should_see("You don't have access to this page.", retries=30)
    await user.should_not_see(marker="programmes")
