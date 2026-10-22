import asyncio

from nicegui import ui
from nicegui.testing import User

from pmp_frontend import api
from pmp_frontend.chat_page import linked
from tests.conftest import STARTING_ACCOUNTS, eventually, ready_to_work


async def api_token(role: str) -> str:
    """A starting account's token, through the API, past the password change."""
    email, password = STARTING_ACCOUNTS[role]
    token, _ = await api.login(email, password)
    await api.change_password(token, password, f"{role}-api-password")
    return token


async def drone_with_the_student(token: str) -> int:
    """A Project "Drone" owned by the Teacher, with the starting Student in it."""
    teachers = await api.teachers(token)
    owner = next(t["id"] for t in teachers if t["name"] == "Teacher Account")
    project = await api.create_project(
        token,
        {
            "title": "Drone",
            "description": None,
            "product_owner_id": owner,
            "team_size_min": 1,
            "team_size_max": 3,
        },
    )
    students = await api.students(token)
    student = next(s["id"] for s in students if s["name"] == "Student Account")
    await api.add_member(token, project["id"], student)
    return project["id"]


def found(user: User, marker: str) -> list:
    """The visible elements with `marker`, or none yet."""
    try:
        return list(user.find(marker=marker).elements)
    except AssertionError:
        return []


def navigation_targets(user: User) -> set[str]:
    """Where the visible navigation items lead; hidden items aren't found."""
    return {link.props.get("href") for link in found(user, "navigation")}


def bodies(user: User) -> list[str]:
    shown = sorted(found(user, "message-body"), key=lambda element: element.id)
    return [element.content for element in shown]


async def test_a_student_chats_with_the_product_owner(user: User):
    superuser = await api_token("superuser")
    drone = await drone_with_the_student(superuser)
    await ready_to_work(user, "student")

    await user.open("/chat")
    await user.should_see("Chat: Drone", retries=30)
    await eventually(lambda: "/chat" in navigation_targets(user))
    await user.should_see("No messages yet.")
    user.find(marker="chat-input").type("Who brings the soldering iron?")
    user.find(marker="chat-send").click()
    await eventually(lambda: bodies(user) == ["Who brings the soldering iron?"])
    await user.should_not_see("No messages yet.")

    # Another person's message appears without reloading (polling, ADR 0008).
    teacher = await api_token("teacher")
    await api.send_chat_message(teacher, drone, "I do: https://vives.be.")
    await eventually(lambda: len(bodies(user)) == 2, retries=100)
    assert bodies(user)[1] == (
        'I do: <a href="https://vives.be" target="_blank" '
        'rel="noopener noreferrer">https://vives.be</a>.'
    )


async def test_a_teacher_sees_unread_messages_and_opens_the_chat(user: User):
    superuser = await api_token("superuser")
    drone = await drone_with_the_student(superuser)
    student = await api_token("student")
    await api.send_chat_message(student, drone, "Can we meet on Friday?")
    await ready_to_work(user, "teacher")

    await user.open("/chats")
    await user.should_see(marker="chats", retries=30)
    badge = user.find(marker="chat-badge").elements.pop()
    assert isinstance(badge, ui.badge)
    await eventually(lambda: badge.text == "1" and badge.visible, retries=100)
    table = user.find(marker="chats").elements.pop()
    assert isinstance(table, ui.table)
    assert [(row["title"], row["unread"]) for row in table.rows] == [("Drone", 1)]

    await user.open(f"/chats/{drone}")
    await user.should_see("Chat: Drone", retries=30)
    await eventually(lambda: bodies(user) == ["Can we meet on Friday?"])
    # Opening the chat reads it (before the page is shown).
    email, _ = STARTING_ACCOUNTS["teacher"]
    teacher, _ = await api.login(email, "teacher-own-password")
    assert (await api.chats(teacher))[0]["unread"] == 0


async def test_a_project_page_links_to_its_chat(user: User):
    superuser = await api_token("superuser")
    drone = await drone_with_the_student(superuser)
    await ready_to_work(user, "teacher")

    await user.open(f"/projects/{drone}")
    await user.should_see(marker="open-chat", retries=30)
    user.find(marker="open-chat").click()

    await user.should_see("Chat: Drone", retries=30)


async def test_a_student_without_a_project_has_no_chat_item(user: User):
    await ready_to_work(user, "student")
    await user.open("/my-project")
    await user.should_see(marker="navigation", retries=30)

    # Shown only once the backend says there is a Chat (checked 0.1 s after the
    # page loads): never, here.
    await user.should_see("You haven't been assigned to a project yet.", retries=30)
    await asyncio.sleep(1)
    assert "/my-project" in navigation_targets(user)
    assert "/chat" not in navigation_targets(user)


def test_links_are_escaped_and_clickable():
    assert linked("<b>hi</b> see http://x.be/a?b=1&c=2, ok") == (
        "&lt;b&gt;hi&lt;/b&gt; see "
        '<a href="http://x.be/a?b=1&amp;c=2" target="_blank" '
        'rel="noopener noreferrer">http://x.be/a?b=1&amp;c=2</a>, ok'
    )
