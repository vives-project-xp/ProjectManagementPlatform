"""Also on TikTok in Review and on Scheduled posts (spec #145, #147)."""

import asyncio
from datetime import datetime
from pathlib import Path

from nicegui import ui
from nicegui.testing import User

from pmp_backend.services import suggestions, tiktok_posts
from pmp_backend.testing import FakeLLM
from pmp_frontend import api
from tests.conftest import ready_to_work
from tests.test_chat import api_token, drone_with_the_student
from tests.test_social import WEDNESDAY_17, photo, short_clip


async def suggestion_with_video(backend, tmp_path: Path) -> tuple[str, int]:
    """Drone's Weekly update with a photo, a video and the AI's suggestion;
    the Superuser's token and the suggestion id."""
    staff = await api_token("superuser")
    await api.set_social_settings(staff, WEDNESDAY_17)
    await drone_with_the_student(staff)
    student, _ = await api.login("student@pmp.local", "student-secret-1")
    await api.change_password(student, "student-secret-1", "student-api-password")
    await api.save_weekly_update(student, "We tested the motors.")
    await api.upload_weekly_photo(
        student, "photo.jpg", photo(), "image/jpeg", consent=True
    )
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(short_clip(tmp_path))
    await api.upload_weekly_video(student, clip, "clip.mp4", "video/mp4", consent=True)

    async def video_ready() -> bool:
        mine = await api.my_weekly_update(student)
        return any(
            m["kind"] == "video" and m["state"] == "ready"
            for m in mine["current"]["media"]
        )

    for _ in range(120):
        if await video_ready():
            break
        await asyncio.sleep(0.25)
    mine = await api.my_weekly_update(student)
    backend.state.llm = FakeLLM()
    closes = datetime.fromisoformat(mine["current"]["closes_at"])
    with backend.state.sessionmaker() as session:
        suggestions.run_once(
            session,
            backend.state.llm,
            tmp_path / "social-media",
            suggestions.generate_at(closes),
        )
    [found] = await api.post_suggestions(staff)
    assert found["has_video"], found
    return staff, found["id"]


async def test_a_reviewer_posts_with_also_on_tiktok(
    user: User, backend_in_process, tmp_path: Path
) -> None:
    staff, suggestion = await suggestion_with_video(backend_in_process, tmp_path)
    await ready_to_work(user, "teacher")
    await user.open("/post-suggestions")
    await user.should_see(marker="also-on-tiktok")

    user.find(marker="also-on-tiktok").elements.pop().set_value(True)
    await user.should_see("Music Usage Confirmation")
    user.find(marker="post-suggestion").click()
    await user.should_see("Choose who can see the video on TikTok.")

    privacy = user.find(marker="tiktok-privacy").elements.pop()
    assert isinstance(privacy, ui.select)
    assert privacy.value is None
    privacy.set_value("SELF_ONLY")
    user.find(marker="post-suggestion").click()
    await user.should_see("Post this?")
    user.find(marker="confirm").click()

    await user.should_see("On TikTok:", retries=30)
    [found] = await api.post_suggestions(staff)
    assert found["tiktok"]["state"] == "scheduled"
    assert found["tiktok"]["privacy_level"] == "SELF_ONLY"
    await user.should_see(marker="tiktok-line")


async def test_a_tiktok_video_posted_by_hand(
    user: User, backend_in_process, tmp_path: Path
) -> None:
    staff, suggestion = await suggestion_with_video(backend_in_process, tmp_path)
    done = await api.post_suggestion(
        staff, suggestion, {"also_on_tiktok": True, "privacy_level": "SELF_ONLY"}
    )
    moment = datetime.fromisoformat(done["tiktok"]["scheduled_for"])
    with backend_in_process.state.sessionmaker() as session:
        tiktok_posts.publish_due(
            session,
            backend_in_process.state.tiktok,
            backend_in_process.state.settings,
            moment,
        )
    await ready_to_work(user, "teacher")
    await user.open("/scheduled-posts")
    await user.should_see(marker=f"tiktok-to-post-{suggestion}")
    await user.should_see(marker="tiktok-notice")
    await user.should_see(marker="download-tiktok-video")

    user.find(marker="mark-tiktok-posted").click()
    await user.should_see("on TikTok?")
    user.find(marker="confirm").click()

    await user.should_see("Marked as posted on TikTok.", retries=30)
    [found] = await api.post_suggestions(staff)
    assert found["tiktok"]["state"] == "posted_by_hand"


async def test_pull_back_from_tiktok_only(
    user: User, backend_in_process, tmp_path: Path
) -> None:
    staff, suggestion = await suggestion_with_video(backend_in_process, tmp_path)
    await api.post_suggestion(
        staff, suggestion, {"also_on_tiktok": True, "privacy_level": "SELF_ONLY"}
    )
    await ready_to_work(user, "teacher")
    await user.open("/scheduled-posts")
    await user.should_see(marker=f"tiktok-scheduled-{suggestion}")

    user.find(marker=f"tiktok-row-pull-back-{suggestion}").click()

    await user.should_see("The video was taken off TikTok's line.", retries=30)
    [found] = await api.post_suggestions(staff)
    assert found["tiktok"] is None and found["state"] == "scheduled"
