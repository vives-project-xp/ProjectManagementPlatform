from datetime import date, timedelta

from nicegui.testing import User

from pmp_frontend import api
from tests.conftest import eventually, ready_to_work
from tests.test_chat import api_token, bodies, drone_with_the_student, found


async def test_a_teacher_reads_an_archived_chat_with_its_deletion_date(user: User):
    superuser = await api_token("superuser")
    drone = await drone_with_the_student(superuser)
    student = await api_token("student")
    await api.send_chat_message(student, drone, "Our last message")
    await api.archive_project(superuser, drone)
    await ready_to_work(user, "teacher")

    await user.open(f"/chats/{drone}")

    await user.should_see(marker="chat-archived", retries=30)
    await user.should_see("This Project is archived: its chat is read-only.")
    day = (date.today() + timedelta(days=182)).strftime("%d/%m/%Y")
    await user.should_see(f"This chat will be deleted on {day}.")
    await eventually(lambda: bodies(user) == ["Our last message"])
    assert not found(user, "chat-input")
    assert not found(user, "message-menu-1")
    assert not found(user, "react-1")
