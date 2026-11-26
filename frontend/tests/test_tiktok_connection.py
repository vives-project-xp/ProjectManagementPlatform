"""Connect TikTok and TikTok's Posting times on the Social media screen
(spec #145, #146)."""

from nicegui import ui
from nicegui.testing import User

from pmp_frontend import api
from tests.conftest import ready_to_work


async def test_the_superuser_connects_tiktok(user: User) -> None:
    await ready_to_work(user, "superuser")
    await user.open("/social-media")
    await user.should_see(marker="tiktok-not-connected")
    await user.should_see(marker="connect-tiktok")

    user.find(marker="send-tiktok-code").click()
    await user.should_see("Paste the address TikTok sent you to.")

    user.find(marker="tiktok-pasted").type("the-code")
    user.find(marker="send-tiktok-code").click()

    await user.should_see("TikTok is connected.")
    await user.should_see(marker="tiktok-connected")
    await user.should_see("Connect again")


async def test_a_refused_code_shows_why(user: User, backend_in_process) -> None:
    backend_in_process.state.tiktok.refused.add("old-code")
    await ready_to_work(user, "superuser")
    await user.open("/social-media")
    await user.should_see(marker="tiktok-pasted")

    user.find(marker="tiktok-pasted").type("old-code")
    user.find(marker="send-tiktok-code").click()

    await user.should_see("a code works only once", retries=30)
    await user.should_not_see(marker="tiktok-connected")


async def test_the_superuser_sets_tiktoks_posting_times(user: User) -> None:
    await ready_to_work(user, "superuser")
    await user.open("/social-media")
    await user.should_see(marker="tiktok-weekdays")
    days = user.find(marker="tiktok-weekdays").elements.pop()
    assert isinstance(days, ui.select)
    days.set_value([1, 3])
    user.find(marker="tiktok-time-1").elements.pop().set_value("16:30")
    user.find(marker="slideshow-cutoff-time").elements.pop().set_value("09:00")
    user.find(marker="save-social-settings").click()

    await user.should_see("The social media settings were saved.")
    token = await api.login("superuser@pmp.local", "superuser-own-password")
    saved = await api.social_settings(token[0])
    assert (saved["tiktok_weekdays"], saved["tiktok_times"]) == ([1, 3], ["16:30"])
    assert saved["slideshow_cutoff_time"] == "09:00"
    assert (saved["slideshow_weekday"], saved["slideshow_time"]) == (4, "18:00")
