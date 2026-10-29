from nicegui.testing import User

from pmp_frontend import api
from tests.conftest import eventually, ready_to_work
from tests.test_chat import api_token, bodies, drone_with_the_student, found


def texts(user: User, marker: str) -> list[str]:
    """The text of every label inside the elements with `marker`."""
    return [
        child.text
        for element in found(user, marker)
        for child in element.descendants()
        if hasattr(child, "text") and child.text
    ]


async def open_student_chat(user: User) -> tuple[int, str]:
    """The Drone chat with one message by the Teacher: its id, and the Teacher's
    token."""
    drone = await drone_with_the_student(await api_token("superuser"))
    teacher = await api_token("teacher")
    sent = await api.send_chat_message(teacher, drone, "Who brings the drone?")
    await ready_to_work(user, "student")
    await user.open("/chat")
    await user.should_see(marker=f"message-menu-{sent['id']}", retries=30)
    await user.should_see(marker="chat-input", retries=30)
    return sent["id"], teacher


async def test_a_student_replies_with_a_quote(user: User):
    question, _ = await open_student_chat(user)

    user.find(marker=f"reply-{question}").click()
    await user.should_see("Replying to Teacher Account: Who brings the drone?")
    user.find(marker="chat-input").type("I do")
    user.find(marker="chat-send").click()

    await eventually(lambda: bodies(user) == ["Who brings the drone?", "I do"])
    await eventually(lambda: bool(found(user, "quote-2")))
    assert texts(user, "quote-2") == ["Teacher Account", "Who brings the drone?"]
    await eventually(lambda: not found(user, "chat-replying"))
    # Clicking the quote scrolls to the original (in the browser).
    user.find(marker="quote-2").click()


async def test_a_student_edits_and_deletes_their_own_message(user: User):
    question, _ = await open_student_chat(user)
    # Someone else's message: Reply only.
    assert not found(user, f"edit-{question}")
    assert not found(user, f"delete-{question}")
    user.find(marker="chat-input").type("Meeting at 10")
    user.find(marker="chat-send").click()
    await user.should_see(marker="edit-2", retries=30)

    user.find(marker="edit-2").click()
    await user.should_see(marker="edit-input")
    user.find(marker="edit-input").clear().type("Meeting at 11")
    user.find(marker="save-edit").click()
    await eventually(lambda: bodies(user) == ["Who brings the drone?", "Meeting at 11"])
    await user.should_see("(edited)")

    user.find(marker="delete-2").click()
    await user.should_see("Delete this message? Its files go too.")
    user.find(marker="confirm").click()
    await user.should_see("This message was deleted.", retries=30)
    assert bodies(user) == ["Who brings the drone?"]


async def test_edits_and_deletions_by_others_appear_live(user: User):
    question, teacher = await open_student_chat(user)

    await api.edit_chat_message(teacher, question, "Who brings the charger?")
    await eventually(lambda: bodies(user) == ["Who brings the charger?"], retries=100)

    await api.delete_chat_message(teacher, question)
    await eventually(lambda: bool(found(user, "message-deleted")), retries=100)
    assert bodies(user) == []


async def test_a_teacher_deletes_a_students_message_and_its_quote_says_so(
    user: User,
):
    drone = await drone_with_the_student(await api_token("superuser"))
    student = await api_token("student")
    rude = await api.send_chat_message(student, drone, "Something rude")
    await api.send_chat_message(student, drone, "Sorry", reply_to_id=rude["id"])
    await ready_to_work(user, "teacher")
    await user.open(f"/chats/{drone}")
    await user.should_see(marker=f"delete-{rude['id']}", retries=30)

    user.find(marker=f"delete-{rude['id']}").click()
    await user.should_see("Delete this message? Its files go too.")
    user.find(marker="confirm").click()

    await eventually(lambda: bool(found(user, "message-deleted")), retries=100)
    await eventually(
        lambda: (
            texts(user, "quote-2") == ["Student Account", "This message was deleted."]
        )
    )
    assert bodies(user) == ["Sorry"]
