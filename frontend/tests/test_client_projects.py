"""Clients on Projects (#134): staff link one; the Client opens the page."""

from nicegui.testing import User

from pmp_frontend import api
from tests.conftest import eventually, ready_to_work
from tests.test_chat import api_token, drone_with_the_student

JAN = {
    "role": "client",
    "first_name": "Jan",
    "last_name": "Peeters",
    "email": "jan@barco.example",
    "organisation": "Barco",
}


async def test_staff_link_a_client_and_give_the_label(user: User):
    staff = await api_token("superuser")
    project = await drone_with_the_student(staff)
    created = await api.create_user(staff, JAN)
    await ready_to_work(user, "teacher")
    await user.open(f"/projects/{project}")
    await user.should_see(marker="client-choice", retries=30)

    choice = user.find(marker="client-choice").elements.pop()
    choice.set_value(next(iter(choice.options)))
    user.find(marker="add-client").click()
    await user.should_see(marker=f"client-{created['id']}", retries=30)
    user.find(marker="make-client-product-owner").click()

    await user.should_see("Jan Peeters (Barco), Client Product Owner", retries=30)
    details = await api.get_project(staff, project)
    assert details["clients"][0]["is_client_product_owner"] is True


async def test_a_client_opens_a_followed_project(user: User):
    staff = await api_token("superuser")
    project = await drone_with_the_student(staff)
    created = await api.create_user(staff, JAN)
    await api.add_client(staff, project, created["id"])
    token, _ = await api.login("jan@barco.example", created["temporary_password"])
    await api.change_password(token, created["temporary_password"], "client-password")

    await user.open("/login")
    user.find(marker="email").type("jan@barco.example")
    user.find(marker="password").type("client-password")
    user.find(marker="log-in").click()
    await user.should_see(marker=f"followed-{project}", retries=30)
    await user.open(f"/my-projects/{project}")

    await user.should_see(marker="followed-team", retries=30)
    await user.should_see("Student Account")
    await user.should_see("Product Owner: Teacher Account")
    await eventually(lambda: bool(user.find(marker="my-planning").elements))
