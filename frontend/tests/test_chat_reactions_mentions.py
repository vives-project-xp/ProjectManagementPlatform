from nicegui import ui
from nicegui.testing import User

from pmp_frontend import api
from pmp_frontend.chat_page import linked
from tests.conftest import eventually, ready_to_work
from tests.test_chat import api_token, drone_with_the_student, found
from tests.test_chat_edit_delete import open_student_chat


def button_text(user: User, marker: str) -> str | None:
    shown = found(user, marker)
    return shown[0].text if shown and isinstance(shown[0], ui.button) else None


def test_mentions_are_bold_but_links_stay_intact():
    assert linked("Hi @teacher account and @team!", ["Teacher Account"]) == (
        "Hi <b>@teacher account</b> and <b>@team</b>!"
    )
    assert linked("@Nobody here", ["Teacher Account"]) == "@Nobody here"
    assert linked("https://x.be/@team", ["Teacher Account"]) == (
        '<a href="https://x.be/@team" target="_blank" rel="noopener noreferrer">'
        "https://x.be/@team</a>"
    )


async def test_a_student_reacts_and_sees_others_reactions_live(user: User):
    question, teacher = await open_student_chat(user)

    user.find(marker=f"react-{question}-party").click()
    await eventually(lambda: button_text(user, f"reaction-{question}-party") == "🎉 1")

    await api.add_chat_reaction(teacher, question, "🎉")
    await eventually(
        lambda: button_text(user, f"reaction-{question}-party") == "🎉 2", retries=100
    )

    # Clicking your own reaction takes it back.
    user.find(marker=f"reaction-{question}-party").click()
    await eventually(lambda: button_text(user, f"reaction-{question}-party") == "🎉 1")


async def test_a_student_mentions_the_product_owner(user: User):
    _, teacher = await open_student_chat(user)

    user.find(marker="chat-input").type("Thanks @Tea")
    await user.should_see(marker="mention-suggestions", retries=30)
    user.find(marker="mention-option", content="@Teacher Account").click()
    box = user.find(marker="chat-input").elements.pop()
    assert isinstance(box, ui.textarea)
    await eventually(lambda: box.value == "Thanks @Teacher Account ")
    user.find(marker="chat-send").click()

    await eventually(lambda: bool(found(user, "message-2")))
    assert (await api.chat_unread(teacher))["mentioned"] is True


async def test_a_mentioned_teacher_sees_the_marker_and_the_highlight(user: User):
    drone = await drone_with_the_student(await api_token("superuser"))
    student = await api_token("student")
    await api.send_chat_message(student, drone, "@Teacher Account please check")
    await ready_to_work(user, "teacher")

    await user.open("/chats")
    await user.should_see(marker="chats", retries=30)
    marker = user.find(marker="chat-mention").elements.pop()
    await eventually(lambda: marker.visible, retries=100)

    await user.open(f"/chats/{drone}")
    await user.should_see(marker="mentioned-1", retries=30)
