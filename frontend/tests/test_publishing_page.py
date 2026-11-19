"""What staff see about automatic publishing on Scheduled posts (#117)."""

from nicegui.testing import User

from pmp_frontend.scheduled_page import channel_notice
from pmp_frontend.social_page import outcome_text
from tests.conftest import ready_to_work

ON = {
    "automatic": True,
    "photos_automatic": True,
    "expires_at": "2027-01-18T10:00:00+00:00",
    "refresh_error": None,
}


def test_no_notice_while_everything_is_published_automatically() -> None:
    assert channel_notice(ON) is None


def test_notices_say_what_isnt_automatic() -> None:
    assert "isn't set up" in channel_notice(ON | {"automatic": False})
    assert "photo posts come here" in channel_notice(ON | {"photos_automatic": False})
    refresh = channel_notice(ON | {"refresh_error": "Instagram answered 400"})
    assert refresh.startswith("Instagram's token couldn't be refreshed")
    assert "18/01/2027" in refresh


def test_a_published_week_reads_as_published() -> None:
    week = {"suggestion_state": "published", "published_url": "https://x"}

    assert outcome_text(week) == "Published on Instagram."


async def test_staff_are_told_publishing_isnt_set_up(user: User) -> None:
    await ready_to_work(user, "teacher")
    await user.open("/scheduled-posts")

    await user.should_see(marker="channel-notice", retries=30)
    await user.should_see("Automatic publishing on Instagram isn't set up")
