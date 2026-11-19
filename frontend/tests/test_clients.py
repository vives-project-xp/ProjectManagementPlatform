"""Clients (#133): the Superuser creates one; the Client logs in to My projects."""

from nicegui.testing import User

from pmp_frontend import api
from tests.conftest import eventually, ready_to_work
from tests.test_chat import api_token, navigation_targets
from tests.test_users import table_emails


async def test_the_superuser_creates_a_client_with_an_organisation(user: User):
    await ready_to_work(user, "superuser")
    await user.open("/users")
    await user.should_see(marker="users", retries=30)

    user.find(marker="new-user").click()
    user.find(marker="role").elements.pop().set_value("client")
    user.find(marker="first-name").type("Jan")
    user.find(marker="last-name").type("Peeters")
    user.find(marker="new-email").type("jan@barco.example")
    user.find(marker="organisation").type("Barco")
    user.find(marker="create-user").click()

    await user.should_see("Jan Peeters was created.")
    await eventually(lambda: "jan@barco.example" in table_emails(user))
    await user.should_see("Barco")


async def test_a_client_logs_in_to_my_projects(user: User):
    staff = await api_token("superuser")
    created = await api.create_user(
        staff,
        {
            "role": "client",
            "first_name": "Jan",
            "last_name": "Peeters",
            "email": "jan@barco.example",
            "organisation": "Barco",
        },
    )

    await user.open("/login")
    user.find(marker="email").type("jan@barco.example")
    user.find(marker="password").type(created["temporary_password"])
    user.find(marker="log-in").click()
    await user.should_see("Change your password", retries=30)
    user.find(marker="current-password").type(created["temporary_password"])
    user.find(marker="new-password").type("client-own-password")
    user.find(marker="repeat-password").type("client-own-password")
    user.find(marker="change-password").click()

    await user.should_see(marker="no-projects", retries=30)
    assert navigation_targets(user) == {"/my-projects"}
    await user.open("/account")
    await user.should_see("Change your password", retries=30)
    await user.should_not_see(marker="github-card")
    await user.should_not_see("Daily email")
