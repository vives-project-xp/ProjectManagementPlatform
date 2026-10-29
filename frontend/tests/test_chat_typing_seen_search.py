from nicegui import ui
from nicegui.testing import User

from pmp_frontend import api
from pmp_frontend.chat_page import typing_line
from tests.conftest import eventually
from tests.test_chat import found
from tests.test_chat_edit_delete import open_student_chat


def label_text(user: User, marker: str) -> str | None:
    shown = found(user, marker)
    return shown[0].text if shown else None


def test_the_typing_line_names_everyone():
    assert typing_line([]) == ""
    assert typing_line(["Anna"]) == "Anna is typing…"
    assert typing_line(["Anna", "Bram"]) == "Anna and Bram are typing…"
    assert typing_line(["Anna", "Bram", "Cas"]) == "Anna, Bram and Cas are typing…"


async def test_a_student_sees_the_teacher_typing(user: User):
    drone_message, teacher = await open_student_chat(user)
    chat = (await api.chats(teacher))[0]

    await api.chat_typing(teacher, chat["project_id"])

    await eventually(
        lambda: label_text(user, "chat-typing") == "Teacher is typing…", retries=100
    )


async def test_seen_by_follows_reading(user: User):
    _, teacher = await open_student_chat(user)
    drone = (await api.chats(teacher))[0]["project_id"]
    user.find(marker="chat-input").type("Can you check my code?")
    user.find(marker="chat-send").click()
    await user.should_see(marker="seen-by-2", retries=30)
    assert user.find(marker="seen-by-2").elements.pop().text == "Not seen yet"

    await api.mark_chat_read(teacher, drone, 2)

    await eventually(lambda: label_text(user, "seen-by-2") == "Seen by 1", retries=100)
    await user.should_see("Teacher Account")


async def test_search_finds_a_message_and_jumps_to_it(user: User):
    _, teacher = await open_student_chat(user)
    drone = (await api.chats(teacher))[0]["project_id"]
    await api.send_chat_message(teacher, drone, "The budget is 300 euro")
    await user.should_see(marker="message-2", retries=100)

    user.find(marker="chat-search").click()
    user.find(marker="search-text").type("BUDGET")
    user.find(marker="search-run").click()

    await user.should_see(marker="search-result-2", retries=30)
    assert not found(user, "search-result-1")
    user.find(marker="search-result-2").click()

    files_only = user.find(marker="search-files-only").elements.pop()
    assert isinstance(files_only, ui.checkbox)
    files_only.value = True
    user.find(marker="search-run").click()
    await user.should_see("Nothing found.", retries=30)
