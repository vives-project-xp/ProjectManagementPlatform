from nicegui import ui
from nicegui.testing import User

from pmp_frontend import api
from tests.conftest import eventually, ready_to_work
from tests.test_chat import api_token, found, navigation_targets


async def project_owned_by_the_teacher(token: str, title: str) -> int:
    teachers = await api.teachers(token)
    owner = next(t["id"] for t in teachers if t["name"] == "Teacher Account")
    project = await api.create_project(
        token,
        {
            "title": title,
            "description": None,
            "product_owner_id": owner,
            "team_size_min": 1,
            "team_size_max": 3,
        },
    )
    return project["id"]


async def the_student(token: str) -> int:
    students = await api.students(token)
    return next(s["id"] for s in students if s["name"] == "Student Account")


async def test_a_teacher_adds_and_removes_a_guest(user: User):
    superuser = await api_token("superuser")
    drone = await project_owned_by_the_teacher(superuser, "Drone")
    student = await the_student(superuser)
    await ready_to_work(user, "teacher")

    await user.open(f"/chats/{drone}")
    await user.should_see(marker="add-guest", retries=30)
    user.find(marker="add-guest").click()
    await user.should_see(marker="guest-choice", retries=30)
    choice = user.find(marker="guest-choice").elements.pop()
    assert isinstance(choice, ui.select)
    choice.set_value(student)
    user.find(marker="confirm-add-guest").click()

    await user.should_see("Student Account joined the chat as a Guest.", retries=30)
    await user.should_see(marker=f"remove-guest-{student}", retries=30)
    await user.should_see("People (2)")

    user.find(marker=f"remove-guest-{student}").click()
    await user.should_see("Remove Student Account from this chat?", retries=10)
    user.find(marker="confirm").click()
    await user.should_see("Student Account was removed from the chat.", retries=30)
    await user.should_see("People (1)", retries=30)


async def test_a_student_guest_chats_and_leaves(user: User):
    superuser = await api_token("superuser")
    drone = await project_owned_by_the_teacher(superuser, "Drone")
    await api.add_chat_guest(superuser, drone, await the_student(superuser))
    await ready_to_work(user, "student")

    # A Guest without a Project still gets the Chat item, straight into the chat.
    await eventually(lambda: "/chat" in navigation_targets(user), retries=100)
    await user.open("/chat")
    await user.should_see("Chat: Drone", retries=30)
    assert not found(user, "add-guest")

    user.find(marker="leave-chat").click()
    await user.should_see("Leave this chat?", retries=10)
    user.find(marker="confirm").click()

    await user.should_see("You left the chat.", retries=30)
    assert await api.chats(superuser) == [
        {"project_id": drone, "title": "Drone", "unread": 0, "mine": False}
    ]


async def test_only_my_chats_is_on_by_default(user: User):
    teacher = await api_token("teacher")
    await project_owned_by_the_teacher(teacher, "Drone")
    await ready_to_work(user, "superuser")

    await user.open("/chats")
    await user.should_see("You're not in any chat yet", retries=30)
    switch = user.find(marker="only-my-chats").elements.pop()
    assert isinstance(switch, ui.switch)
    switch.set_value(False)

    await user.should_see(marker="chats", retries=30)
    table = user.find(marker="chats").elements.pop()
    assert [row["title"] for row in table.rows] == ["Drone"]


async def test_a_student_in_two_chats_chooses_one(user: User):
    superuser = await api_token("superuser")
    drone = await project_owned_by_the_teacher(superuser, "Drone")
    robot = await project_owned_by_the_teacher(superuser, "Robot")
    student = await the_student(superuser)
    await api.add_member(superuser, robot, student)
    await api.add_chat_guest(superuser, drone, student)
    await ready_to_work(user, "student")

    await user.open("/chat")
    await user.should_see(marker="chats", retries=30)
    table = user.find(marker="chats").elements.pop()
    assert [row["title"] for row in table.rows] == ["Drone", "Robot"]
