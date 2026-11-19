"""Earlier weeks' outcomes and the 4-month clean-up on the Weekly update page
(#118)."""

from datetime import datetime, timedelta

import pytest
from nicegui.testing import User
from sqlalchemy import create_engine, text

from pmp_backend import testing
from pmp_backend.services import social
from pmp_frontend import api
from pmp_frontend.social_page import MEDIA_REMOVED, outcome_text
from tests.conftest import log_in
from tests.test_chat import api_token, drone_with_the_student
from tests.test_social import WEDNESDAY_17, photo

SOON = "2026-12-02T11:00:00+00:00"


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        (None, "No Post suggestion this week."),
        ("failed", "No Post suggestion this week."),
        ("generating", "Post suggestion waiting for Review."),
        ("waiting", "Post suggestion waiting for Review."),
        ("scheduled", "Scheduled to be posted on 02/12/2026 12:00"),
        ("to_post_by_hand", "Scheduled to be posted on 02/12/2026 12:00"),
        ("published", "Published on Instagram."),
        ("posted_by_hand", "Posted on social media on 02/12/2026 12:00"),
        ("refused", "Not posted on social media this week: Too dark."),
    ],
)
def test_each_outcome_reads_plainly(state: str | None, expected: str) -> None:
    week = {
        "suggestion_state": state,
        "refusal_reason": "Too dark.",
        "scheduled_for": SOON,
        "posted_at": SOON,
    }

    assert outcome_text(week).startswith(expected)


async def test_a_cleaned_up_week_keeps_its_text_and_outcome(
    user: User, backend_in_process
) -> None:
    staff = await api_token("superuser")
    await api.set_social_settings(staff, WEDNESDAY_17)
    await drone_with_the_student(staff)
    student, _ = await api.login("student@pmp.local", "student-secret-1")
    await api.change_password(student, "student-secret-1", "student-api-password")
    await api.save_weekly_update(student, "We tested the motors.")
    await api.upload_weekly_photo(
        student, "photo.jpg", photo(), "image/jpeg", consent=True
    )
    engine = create_engine(testing.TEST_DATABASE_URL)
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE weekly_updates SET closes_at = closes_at - interval '130 days'"
            )
        )
    engine.dispose()
    settings = backend_in_process.state.settings
    with backend_in_process.state.sessionmaker() as session:
        social.clean_up(session, settings.social_media_dir, datetime.now().astimezone())

    await log_in(user, "student", "student-api-password")
    await user.should_see(marker="navigation", retries=30)
    await user.open("/weekly-update")

    await user.should_see("We tested the motors.", retries=30)
    await user.should_see(MEDIA_REMOVED)
    await user.should_see("No Post suggestion this week.")
    [week] = (await api.my_weekly_update(student))["earlier"]
    assert week["media"] == []
    removed = datetime.fromisoformat(week["media_removed_at"])
    assert removed > datetime.now().astimezone() - timedelta(minutes=5)
