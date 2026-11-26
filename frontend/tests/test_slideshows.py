"""The Weekly slideshow card in Review (spec #145, #149, #150)."""

import asyncio
from datetime import datetime, timedelta
from pathlib import Path

from nicegui.testing import User

from pmp_backend.models import WeeklySlideshow
from pmp_backend.services import slideshows, suggestions
from pmp_backend.testing import FakeLLM
from pmp_frontend import api
from tests.conftest import eventually, ready_to_work
from tests.test_chat import api_token, drone_with_the_student
from tests.test_social import WEDNESDAY_17, photo


async def slideshow_waiting(backend, tmp_path: Path) -> tuple[str, dict]:
    """Drone's week with two photos, its suggestion Posted, and the Weekly
    slideshow put together and written; the Superuser's token and it."""
    staff = await api_token("superuser")
    await api.set_social_settings(staff, WEDNESDAY_17)
    await drone_with_the_student(staff)
    student, _ = await api.login("student@pmp.local", "student-secret-1")
    await api.change_password(student, "student-secret-1", "student-api-password")
    await api.save_weekly_update(student, "We tested the motors.")
    for seed in (1, 2):
        mine = await api.upload_weekly_photo(
            student, "photo.jpg", photo(seed=seed), "image/jpeg", consent=True
        )
    backend.state.llm = FakeLLM()
    closes = datetime.fromisoformat(mine["current"]["closes_at"])
    made = suggestions.generate_at(closes)
    with backend.state.sessionmaker() as session:
        suggestions.run_once(
            session, backend.state.llm, tmp_path / "social-media", made
        )
    [found] = await api.post_suggestions(staff)
    await api.post_suggestion(staff, found["id"])
    with backend.state.sessionmaker() as session:
        slideshows.run_once(session, backend.state.llm, made + timedelta(days=3))
    slideshow = await api.latest_slideshow(staff)
    assert slideshow["state"] == "waiting", slideshow
    return staff, slideshow


async def test_staff_edit_the_slideshows_text(
    user: User, backend_in_process, tmp_path: Path
) -> None:
    staff, slideshow = await slideshow_waiting(backend_in_process, tmp_path)
    await ready_to_work(user, "teacher")
    await user.open("/post-suggestions")
    await user.should_see(marker="slideshow-card")
    for item in slideshow["photos"]:
        await user.should_see(marker=f"slideshow-photo-{item['medium']['id']}")

    user.find(marker="slideshow-title").elements.pop().set_value("Drones in de lucht")
    await eventually(lambda: user.find(marker="save-slideshow").elements.pop().enabled)
    user.find(marker="save-slideshow").click()

    await user.should_see("The slideshow was saved.", retries=30)
    found = await api.latest_slideshow(staff)
    assert found["title"] == "Drones in de lucht"
    assert found["reviewed_by"] == "Teacher Account"


async def saved_order(staff: str, expected: list[int]) -> None:
    """Wait until the slideshow's photos are saved in that order."""
    for _ in range(100):
        found = await api.latest_slideshow(staff)
        if [item["medium"]["id"] for item in found["photos"]] == expected:
            return
        await asyncio.sleep(0.1)
    raise AssertionError(found["photos"])


async def test_staff_reorder_and_remove_photos(
    user: User, backend_in_process, tmp_path: Path
) -> None:
    staff, slideshow = await slideshow_waiting(backend_in_process, tmp_path)
    first, second = (item["medium"]["id"] for item in slideshow["photos"])
    await ready_to_work(user, "teacher")
    await user.open("/post-suggestions")
    await user.should_see(marker=f"slideshow-right-{first}", retries=30)

    user.find(marker=f"slideshow-right-{first}").click()
    await saved_order(staff, [second, first])

    await user.open("/post-suggestions")
    await user.should_see(marker=f"slideshow-remove-{second}", retries=30)
    user.find(marker=f"slideshow-remove-{second}").click()
    await saved_order(staff, [first])


async def test_staff_refuse_the_slideshow(
    user: User, backend_in_process, tmp_path: Path
) -> None:
    staff, _ = await slideshow_waiting(backend_in_process, tmp_path)
    await ready_to_work(user, "teacher")
    await user.open("/post-suggestions")
    await user.should_see(marker="refuse-slideshow")

    user.find(marker="refuse-slideshow").click()
    await user.should_see("Refuse the slideshow?")
    user.find(marker="slideshow-refusal-reason").type("Te weinig deze week.")
    user.find(marker="confirm-slideshow-refusal").click()

    await user.should_see("No slideshow this week: Te weinig deze week.", retries=30)
    found = await api.latest_slideshow(staff)
    assert found["state"] == "refused"


async def test_post_then_the_song_check_gates_posted(
    user: User, backend_in_process, tmp_path: Path
) -> None:
    staff, slideshow = await slideshow_waiting(backend_in_process, tmp_path)
    # Put together long ago: its Posting time has passed, so it goes at once.
    with backend_in_process.state.sessionmaker() as session:
        row = session.get(WeeklySlideshow, slideshow["id"])
        row.created_at = row.created_at - timedelta(days=8)
        session.commit()
    await ready_to_work(user, "teacher")
    await user.open("/post-suggestions")
    await user.should_see(marker="post-slideshow")

    user.find(marker="post-slideshow").click()
    await user.should_see("Post the slideshow?")
    user.find(marker="confirm").click()
    await user.should_see("The slideshow goes out on", retries=30)
    found = await api.latest_slideshow(staff)
    with backend_in_process.state.sessionmaker() as session:
        slideshows.publish_due(
            session,
            backend_in_process.state.tiktok,
            backend_in_process.state.settings,
            datetime.fromisoformat(found["scheduled_for"]) + timedelta(seconds=1),
        )

    await user.open("/scheduled-posts")
    await user.should_see(marker="slideshow-by-hand", retries=30)
    await user.should_see(marker="download-slideshow")
    posted = user.find(marker="mark-slideshow-posted").elements.pop()
    assert not posted.enabled

    user.find(marker="song-check").elements.pop().set_value(True)
    await eventually(lambda: posted.enabled)
    user.find(marker="mark-slideshow-posted").click()

    await user.should_see("The slideshow is marked as posted.", retries=30)
    found = await api.latest_slideshow(staff)
    assert found["state"] == "posted"
