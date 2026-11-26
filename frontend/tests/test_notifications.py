"""Browser notifications for Chat messages (spec #145, #148)."""

from nicegui import ui
from nicegui.testing import User

from pmp_frontend import api
from pmp_frontend.shell import notification_items
from tests.conftest import STARTING_ACCOUNTS, ready_to_work
from tests.test_chat import api_token, drone_with_the_student


async def test_switching_chat_notifications_off(user: User):
    await ready_to_work(user, "student")
    await user.open("/account")
    await user.should_see(marker="allow-notifications", retries=30)
    switch = user.find(marker="chat-notifications").elements.pop()
    assert isinstance(switch, ui.switch)
    assert switch.value is True

    switch.set_value(False)

    await user.should_see("No more notifications for chat messages.", retries=30)
    email, _ = STARTING_ACCOUNTS["student"]
    _, me = await api.login(email, "student-own-password")
    assert me.chat_notifications is False


async def test_a_new_message_becomes_a_notification_that_opens_the_chat(user: User):
    staff = await api_token("superuser")
    project = await drone_with_the_student(staff)
    student, _ = await api.login("student@pmp.local", "student-secret-1")
    await api.change_password(student, "student-secret-1", "student-api-password")
    teacher = await api_token("teacher")
    first = await api.notifications(student, None)

    await api.send_chat_message(teacher, project, "@Student Account the motors?")
    found = await api.notifications(student, first["latest"])

    [item] = notification_items(found["chat"])
    assert item["title"] == "Teacher Account in Drone"
    assert item["body"] == "@ @Student Account the motors?"
    assert item["url"] == f"/chats/{project}"
    assert item["project"] == project
