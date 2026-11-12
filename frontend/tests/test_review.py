"""The Review of Post suggestions (#115)."""

from datetime import datetime
from pathlib import Path

from nicegui.testing import User
from sqlalchemy import create_engine, text

from pmp_backend import testing
from pmp_backend.services import suggestions
from pmp_backend.testing import FakeLLM
from pmp_frontend import api
from tests.conftest import eventually, log_in, ready_to_work
from tests.test_chat import api_token, drone_with_the_student
from tests.test_social import WEDNESDAY_17, photo


async def suggestion_waiting(backend, tmp_path: Path) -> tuple[str, int, str]:
    """Drone (Product Owner: the Teacher, Member: the Student) with a Weekly
    update, a photo and the AI's suggestion; the Superuser's token, the
    suggestion id and the Student's token."""
    staff = await api_token("superuser")
    await api.set_social_settings(staff, WEDNESDAY_17)
    await drone_with_the_student(staff)
    student, _ = await api.login("student@pmp.local", "student-secret-1")
    await api.change_password(student, "student-secret-1", "student-api-password")
    await api.save_weekly_update(student, "We tested the motors.")
    mine = await api.upload_weekly_photo(
        student, "photo.jpg", photo(), "image/jpeg", consent=True
    )
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
    return staff, found["id"], student


async def test_a_teacher_edits_and_saves_a_suggestion(
    user: User, backend_in_process, tmp_path: Path
) -> None:
    staff, suggestion, _ = await suggestion_waiting(backend_in_process, tmp_path)
    await ready_to_work(user, "teacher")
    await user.open("/post-suggestions")
    await user.should_see(marker="suggestion-title")
    assert not user.find(marker="save-suggestion").elements.pop().enabled

    user.find(marker="suggestion-title").elements.pop().set_value("Onze drone vliegt")
    await eventually(lambda: user.find(marker="save-suggestion").elements.pop().enabled)
    user.find(marker="save-suggestion").click()

    await user.should_see("The suggestion was saved.", retries=30)
    [found] = await api.post_suggestions(staff)
    assert found["title"] == "Onze drone vliegt"
    assert found["reviewed_by"] == "Teacher Account"


async def test_a_refusal_with_a_reason_reaches_the_team(
    user: User, backend_in_process, tmp_path: Path
) -> None:
    staff, suggestion, student = await suggestion_waiting(backend_in_process, tmp_path)
    await ready_to_work(user, "teacher")
    await user.open("/post-suggestions")
    await user.should_see(marker="refuse-suggestion")

    user.find(marker="refuse-suggestion").click()
    await user.should_see("Refuse this suggestion?")
    user.find(marker="refusal-reason").type("Too dark this week.")
    user.find(marker="confirm-refusal").click()

    await user.should_see("No post for this Project this week: Too dark this week.")
    # The team sees it once the week is among the earlier ones.
    engine = create_engine(testing.TEST_DATABASE_URL)
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE weekly_updates SET closes_at = closes_at - interval '7 days'")
        )
    engine.dispose()
    mine = await api.my_weekly_update(student)
    assert mine["earlier"][0]["refusal_reason"] == "Too dark this week."


async def test_generate_again_and_only_my_projects(
    user: User, backend_in_process, tmp_path: Path
) -> None:
    staff, suggestion, _ = await suggestion_waiting(backend_in_process, tmp_path)
    # Its password was already changed through the API.
    await log_in(user, "superuser", "superuser-api-password")
    await user.should_see(marker="navigation", retries=30)
    await user.open("/post-suggestions")
    # The Superuser is nobody's Product Owner: "Only my Projects" starts off.
    await user.should_see(marker="generate-again")
    assert not user.find(marker="only-mine").elements.pop().value

    user.find(marker="generate-again").click()
    await user.should_see("Let the AI write this suggestion again?")
    user.find(marker="confirm").click()

    await eventually(lambda: len(backend_in_process.state.llm.requests) == 2)
    await user.should_see("Waiting for Review")
    user.find(marker="only-mine").elements.pop().set_value(True)
    await user.should_see("No Post suggestions yet.")
