from nicegui.testing import User


async def test_login_page_shows_the_platform_without_system_status(user: User):
    await user.open("/login")

    await user.should_see("Project Management Platform")
    await user.should_see(marker="log-in")
    await user.should_not_see("System status")
    await user.should_not_see("Backend: online")


async def test_start_page_sends_a_visitor_to_login(user: User):
    await user.open("/")

    await user.should_see(marker="log-in")
