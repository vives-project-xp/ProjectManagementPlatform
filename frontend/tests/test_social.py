import io
import random
import subprocess
from datetime import datetime
from pathlib import Path

import imageio_ffmpeg
from nicegui import ui
from nicegui.testing import User
from PIL import Image, ImageDraw, ImageFilter

from pmp_backend.services import social, suggestions
from pmp_backend.testing import FakeLLM
from pmp_frontend import api
from tests.conftest import eventually, ready_to_work
from tests.test_chat import api_token, drone_with_the_student, navigation_targets

WEDNESDAY_17 = {
    "upload_weekday": 2,
    "upload_time": "17:00",
    "instagram_weekdays": [0, 1, 2, 3, 4],
    "instagram_times": ["12:00", "19:00"],
    "fixed_hashtags": "#VIVEShogeschool #ElektronicaICT",
}


async def test_the_superuser_sets_the_upload_deadline(user: User) -> None:
    await ready_to_work(user, "superuser")
    assert "/social-media" in navigation_targets(user)

    await user.open("/social-media")
    await user.should_see(marker="upload-weekday")
    weekday = user.find(marker="upload-weekday").elements.pop()
    assert isinstance(weekday, ui.select)
    weekday.set_value(2)
    user.find(marker="upload-time").type("17:00")
    user.find(marker="fixed-hashtags").elements.pop().set_value("#VIVES #EOICT")
    user.find(marker="save-social-settings").click()

    await user.should_see("The social media settings were saved.")
    token = await api.login("superuser@pmp.local", "superuser-own-password")
    saved = await api.social_settings(token[0])
    assert (saved["upload_weekday"], saved["upload_time"]) == (2, "17:00")
    assert saved["fixed_hashtags"] == "#VIVES #EOICT"


async def test_a_wrong_setting_shows_why(user: User) -> None:
    await ready_to_work(user, "superuser")
    await user.open("/social-media")
    await user.should_see(marker="fixed-hashtags")
    user.find(marker="fixed-hashtags").elements.pop().set_value("VIVES")
    user.find(marker="save-social-settings").click()

    await user.should_see('"VIVES" is not a hashtag', retries=30)


async def test_a_member_writes_the_weekly_update(user: User) -> None:
    staff = await api_token("superuser")
    await api.set_social_settings(staff, WEDNESDAY_17)
    project = await drone_with_the_student(staff)

    await ready_to_work(user, "student")
    assert "/weekly-update" in navigation_targets(user)
    await user.open("/weekly-update")
    await user.should_see("This Upload week closes on")
    user.find(marker="weekly-update-text").type("We built the frame.")
    user.find(marker="save-weekly-update").click()

    await user.should_see("Last edited by Student Account", retries=30)
    weeks = await api.project_weekly_updates(staff, project)
    assert [week["text"] for week in weeks] == ["We built the frame."]


async def test_before_the_deadline_is_set_members_wait(user: User) -> None:
    staff = await api_token("superuser")
    await drone_with_the_student(staff)

    await ready_to_work(user, "student")
    await user.open("/weekly-update")

    await user.should_see("The Upload deadline hasn't been set yet.")
    await user.should_not_see(marker="save-weekly-update")


async def test_a_student_without_a_project_has_no_weekly_update(user: User) -> None:
    await ready_to_work(user, "student")
    assert "/weekly-update" not in navigation_targets(user)


async def test_staff_read_the_weekly_updates_on_the_project_page(user: User) -> None:
    staff = await api_token("superuser")
    await api.set_social_settings(staff, WEDNESDAY_17)
    project = await drone_with_the_student(staff)
    student, _ = await api.login("student@pmp.local", "student-secret-1")
    await api.change_password(student, "student-secret-1", "student-api-password")
    await api.save_weekly_update(student, "Tested the motors.")

    await ready_to_work(user, "teacher")
    await user.open(f"/projects/{project}")

    await user.should_see(marker="weekly-updates-card")
    await user.should_see("Tested the motors.")


def photo(blurred: bool = False, seed: int = 1) -> bytes:
    """A sharp (or blurred) JPEG that is large enough for the Quality check."""
    shuffle = random.Random(seed)
    image = Image.new("RGB", (1600, 1200), (120, 130, 140))
    draw = ImageDraw.Draw(image)
    for _ in range(400):
        x, y = shuffle.randrange(1600), shuffle.randrange(1200)
        colour = tuple(shuffle.randrange(30, 220) for _ in range(3))
        draw.rectangle((x, y, x + 60, y + 30), fill=colour)
    if blurred:
        image = image.filter(ImageFilter.GaussianBlur(8))
    out = io.BytesIO()
    image.save(out, "JPEG", quality=92)
    return out.getvalue()


async def upload_to_week(user: User, data: bytes, name: str = "photo.jpg") -> None:
    upload = user.find(marker="photo-upload").elements.pop()
    assert isinstance(upload, ui.upload)
    await upload.handle_uploads(
        [ui.upload.SmallFileUpload(name=name, content_type="image/jpeg", _data=data)]
    )


async def member_on_the_weekly_update(user: User) -> tuple[str, int]:
    staff = await api_token("superuser")
    await api.set_social_settings(staff, WEDNESDAY_17)
    project = await drone_with_the_student(staff)
    await ready_to_work(user, "student")
    await user.open("/weekly-update")
    await user.should_see(marker="photo-upload")
    return staff, project


async def test_uploading_needs_the_consent_tick(user: User) -> None:
    await member_on_the_weekly_update(user)
    upload = user.find(marker="photo-upload").elements.pop()
    assert not upload.enabled

    user.find(marker="consent").click()

    await eventually(lambda: upload.enabled)


async def test_a_member_uploads_and_removes_a_photo(user: User) -> None:
    staff, project = await member_on_the_weekly_update(user)
    user.find(marker="consent").click()

    await upload_to_week(user, photo())

    await user.should_see("1 of 5 photos", retries=30)
    [week] = await api.project_weekly_updates(staff, project)
    [medium] = week["media"]
    await user.should_see(marker=f"medium-{medium['id']}")

    user.find(marker=f"remove-medium-{medium['id']}").click()
    await user.should_see("Remove this photo?")
    user.find(marker="confirm").click()
    await user.should_see("0 of 5 photos", retries=30)


async def test_a_blurry_photo_is_refused_with_the_reason(user: User) -> None:
    await member_on_the_weekly_update(user)
    user.find(marker="consent").click()

    await upload_to_week(user, photo(blurred=True), name="shaky.jpg")

    await user.should_see("shaky.jpg: This photo is blurry", retries=30)
    await user.should_see("0 of 5 photos")


async def test_staff_see_the_photos_on_the_project_page(user: User) -> None:
    staff = await api_token("superuser")
    await api.set_social_settings(staff, WEDNESDAY_17)
    project = await drone_with_the_student(staff)
    student, _ = await api.login("student@pmp.local", "student-secret-1")
    await api.change_password(student, "student-secret-1", "student-api-password")
    mine = await api.upload_weekly_photo(
        student, "photo.jpg", photo(), "image/jpeg", consent=True
    )
    medium = mine["current"]["media"][0]["id"]

    await ready_to_work(user, "teacher")
    await user.open(f"/projects/{project}")

    await user.should_see(marker=f"medium-{medium}")


def short_clip(folder: Path) -> bytes:
    target = folder / "clip.mp4"
    subprocess.run(
        [
            imageio_ffmpeg.get_ffmpeg_exe(), "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "testsrc=size=640x360:rate=10:duration=2",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            str(target),
        ],
        check=True,
    )  # fmt: skip
    return target.read_bytes()


async def test_a_member_uploads_a_video(user: User, tmp_path: Path) -> None:
    staff, project = await member_on_the_weekly_update(user)
    user.find(marker="consent").click()
    upload = user.find(marker="video-upload").elements.pop()
    assert isinstance(upload, ui.upload)

    await upload.handle_uploads(
        [
            ui.upload.SmallFileUpload(
                name="clip.mp4", content_type="video/mp4", _data=short_clip(tmp_path)
            )
        ]
    )

    await user.should_see("1 of 1 video", retries=60)
    [week] = await api.project_weekly_updates(staff, project)
    [medium] = week["media"]
    assert (medium["kind"], medium["state"]) == ("video", "ready")
    await user.should_see(marker=f"medium-{medium['id']}")


async def test_staff_are_warned_when_the_disk_is_full(user: User, monkeypatch) -> None:
    monkeypatch.setattr(social, "DISK_WARNING", 0.0)
    await ready_to_work(user, "superuser")
    await user.open("/social-media")

    await user.should_see(marker="storage-card")
    await user.should_see("more than 80% full")


async def test_staff_see_the_ais_post_suggestion(
    user: User, backend_in_process, tmp_path: Path
) -> None:
    staff = await api_token("superuser")
    await api.set_social_settings(staff, WEDNESDAY_17)
    await drone_with_the_student(staff)
    student, _ = await api.login("student@pmp.local", "student-secret-1")
    await api.change_password(student, "student-secret-1", "student-api-password")
    await api.save_weekly_update(student, "We tested the motors.")
    mine = await api.upload_weekly_photo(
        student, "photo.jpg", photo(), "image/jpeg", consent=True
    )
    closes = datetime.fromisoformat(mine["current"]["closes_at"])
    with backend_in_process.state.sessionmaker() as session:
        suggestions.run_once(
            session,
            FakeLLM(),
            tmp_path / "social-media",
            suggestions.generate_at(closes),
        )

    await ready_to_work(user, "teacher")
    await user.open("/post-suggestions")

    await user.should_see("Waiting for Review")
    await user.should_see("Onze drone zweeft! 🚁")
    await user.should_see(marker=f"medium-{mine['current']['media'][0]['id']}")
