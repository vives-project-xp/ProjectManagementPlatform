from nicegui import ui
from nicegui.testing import User

from tests.conftest import create_project, eventually, ready_to_work


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
    user.find(marker="create-user").click()

    await user.should_see("Lisa Peeters was created.")
    await user.should_see(marker="shown-password")
    await eventually(lambda: "lisa.peeters@student.vives.be" in table_emails(user))


async def test_duplicate_email_is_shown_in_the_dialog(user: User):
    await ready_to_work(user, "superuser")
    await user.open("/users")

    user.find(marker="new-user").click()
    user.find(marker="first-name").type("Copy")
    user.find(marker="last-name").type("Teacher")
    user.find(marker="new-email").type("TEACHER@pmp.local")
    user.find(marker="create-user").click()

    await user.should_see("The email address teacher@pmp.local is already in use.")


async def test_invalid_input_gets_a_readable_message(user: User):
    await ready_to_work(user, "superuser")
    await user.open("/users")

    user.find(marker="new-user").click()
    user.find(marker="first-name").type("Ann")
    user.find(marker="last-name").type("Janssens")
    user.find(marker="new-email").type("not-an-email")
    user.find(marker="create-user").click()

    await user.should_see("Email is not valid.")


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


async def test_superuser_deletes_a_user_after_confirming(user: User):
    await ready_to_work(user, "superuser")

    # User 2 is the Teacher starting account, not linked to any Project.
    await user.open("/users/2")
    await user.should_see(marker="delete-user", retries=30)
    user.find(marker="delete-user").click()
    await user.should_see("Delete the User Teacher Account?", retries=10)
    user.find(marker="confirm").click()

    await user.should_see(marker="users", retries=30)
    await eventually(lambda: "teacher@pmp.local" not in table_emails(user))


async def test_deleting_a_product_owner_is_refused(user: User):
    await ready_to_work(user, "superuser")
    await create_project(user, "Smart Greenhouse")

    await user.open("/users/2")
    await user.should_see(marker="delete-user", retries=30)
    user.find(marker="delete-user").click()
    await user.should_see("Delete the User Teacher Account?", retries=10)
    user.find(marker="confirm").click()

    await user.should_see(
        "Teacher Account is the Product Owner of Smart Greenhouse, so they cannot "
        "be deleted. Deactivate them instead."
    )


async def test_the_superuser_page_has_no_delete(user: User):
    await ready_to_work(user, "superuser")

    await user.open("/users/1")
    await user.should_see(marker="save-user", retries=30)

    await user.should_not_see(marker="delete-user")


async def test_teacher_has_no_users_screen(user: User):
    await ready_to_work(user, "teacher")

    await user.should_not_see("Users")
    await user.open("/users")

    await user.should_see("You don't have access to this page.")


async def test_superuser_resets_a_password_and_sees_it_once(user: User):
    await ready_to_work(user, "superuser")

    # User 2 is the Teacher starting account.
    await user.open("/users/2")
    await user.should_see(marker="reset-password", retries=30)
    user.find(marker="reset-password").click()
    await user.should_see("Reset the password of Teacher Account?", retries=10)
    user.find(marker="confirm").click()

    await user.should_see("Temporary password for Teacher Account", retries=30)
    shown = user.find(marker="shown-password").elements.pop()
    assert isinstance(shown, ui.label)
    assert len(shown.text) == 14


async def test_superuser_imports_students_from_a_csv_file(user: User):
    await ready_to_work(user, "superuser")
    await user.open("/users")
    await user.should_see(marker="import-users", retries=30)

    user.find(marker="import-users").click()
    user.find(marker="import-year").elements.pop().set_value("2")
    upload = user.find(marker="import-file").elements.pop()
    assert isinstance(upload, ui.upload)
    content = (
        b"Firstname,Lastname,email\n"
        b"Lisa,Peeters,lisa@student.vives.be\n"
        b"Stu,Dent,student@pmp.local\n"
    )
    await upload.handle_uploads(
        [
            ui.upload.SmallFileUpload(
                name="users.csv", content_type="text/csv", _data=content
            )
        ]
    )

    await user.should_see("1 User created, 1 line skipped.", retries=30)
    await user.should_see(
        "Line 3: The email address student@pmp.local is already in use."
    )
    user.find(marker="download-passwords").click()
    download = await user.download.next()
    lines = download.content.decode("utf-8-sig").splitlines()
    assert lines[0] == "Firstname,Lastname,email,temporary password"
    assert lines[1].startswith("Lisa,Peeters,lisa@student.vives.be,")
    await eventually(lambda: "lisa@student.vives.be" in table_emails(user))
