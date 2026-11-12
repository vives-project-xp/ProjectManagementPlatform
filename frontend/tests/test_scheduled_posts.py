"""Post, Scheduled posts and To post today (#116)."""

from datetime import datetime
from pathlib import Path

from nicegui.testing import User

from pmp_backend.services import posting
from pmp_frontend import api
from tests.conftest import eventually, ready_to_work
from tests.test_review import suggestion_waiting


async def test_post_is_only_possible_with_everything_saved(
    user: User, backend_in_process, tmp_path: Path
) -> None:
    staff, suggestion, _ = await suggestion_waiting(backend_in_process, tmp_path)
    await ready_to_work(user, "teacher")
    await user.open("/post-suggestions")
    await user.should_see(marker="post-suggestion")
    post = user.find(marker="post-suggestion").elements.pop()
    assert post.enabled

    user.find(marker="suggestion-title").elements.pop().set_value("Changed")
    await eventually(lambda: not post.enabled)

    user.find(marker="suggestion-title").elements.pop().set_value(
        "Onze drone zweeft! 🚁"
    )
    await eventually(lambda: post.enabled)
    user.find(marker="post-suggestion").click()
    await user.should_see("Post this?")
    user.find(marker="confirm").click()

    await user.should_see("Scheduled for", retries=30)
    [found] = await api.post_suggestions(staff)
    assert found["state"] == "scheduled"


async def test_pull_back_from_the_scheduled_posts(
    user: User, backend_in_process, tmp_path: Path
) -> None:
    staff, suggestion, _ = await suggestion_waiting(backend_in_process, tmp_path)
    await api.post_suggestion(staff, suggestion)
    await ready_to_work(user, "teacher")
    await user.open("/scheduled-posts")
    await user.should_see(marker="pull-back")

    user.find(marker="pull-back").click()

    await user.should_see("The post was pulled back to Review.", retries=30)
    [found] = await api.post_suggestions(staff)
    assert found["state"] == "waiting"


async def test_posting_by_hand_from_to_post_today(
    user: User, backend_in_process, tmp_path: Path
) -> None:
    staff, suggestion, _ = await suggestion_waiting(backend_in_process, tmp_path)
    scheduled = await api.post_suggestion(staff, suggestion)
    with backend_in_process.state.sessionmaker() as session:
        posting.run_once(session, datetime.fromisoformat(scheduled["scheduled_for"]))
    await ready_to_work(user, "teacher")
    await user.open("/scheduled-posts")
    await user.should_see(marker=f"to-post-{suggestion}")
    await user.should_see(marker="download-media")

    user.find(marker="copy-caption").click()
    await user.should_see("The caption was copied.")
    user.find(marker="mark-posted").click()
    await user.should_see("Did you post")
    user.find(marker="confirm").click()

    await user.should_see("Marked as posted.", retries=30)
    await user.should_see(marker="nothing-to-post")
    [found] = await api.post_suggestions(staff)
    assert (found["state"], found["posted_by"]) == ("posted_by_hand", "Teacher Account")
