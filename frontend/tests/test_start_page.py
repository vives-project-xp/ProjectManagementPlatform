from nicegui.testing import User


async def test_start_page_shows_platform_and_backend_status(user: User):
    await user.open("/")

    await user.should_see("Project Management Platform")
    await user.should_see("Backend: online")
    await user.should_see("Database: online")
