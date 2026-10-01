from nicegui.testing import User


async def test_login_page_shows_platform_and_backend_status(user: User):
    await user.open("/login")

    await user.should_see("Project Management Platform")
    await user.should_see("Backend: online")
    await user.should_see("Database: online")


async def test_start_page_sends_a_visitor_to_login(user: User):
    await user.open("/")

    await user.should_see("System status")
    await user.should_see(marker="log-in")
