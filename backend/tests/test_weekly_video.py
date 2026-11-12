import subprocess
from pathlib import Path

import imageio_ffmpeg
import pytest
from fastapi.testclient import TestClient

from pmp_backend.services import social, video
from pmp_backend.settings import Settings
from tests.conftest import ready_to_work
from tests.test_weekly_updates import (
    WEDNESDAY_17,
    close_the_open_week,
    drone_team,
    set_settings,
)


def clip(
    folder: Path, seconds: float = 2, size: str = "640x360", container: str = "mp4"
) -> bytes:
    """A test video with sound, made with ffmpeg."""
    target = folder / f"clip-{seconds}-{size}.{container}"
    subprocess.run(
        [
            imageio_ffmpeg.get_ffmpeg_exe(), "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", f"testsrc=size={size}:rate=10:duration={seconds}",
            "-f", "lavfi", "-i", f"sine=duration={seconds}",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest", str(target),
        ],
        check=True,
    )  # fmt: skip
    return target.read_bytes()


@pytest.fixture(scope="module")
def short_clip(tmp_path_factory) -> bytes:
    return clip(tmp_path_factory.mktemp("clips"))


def upload(
    client: TestClient, headers: dict, data: bytes, *, consent=True, name="clip.mp4"
):
    return client.post(
        "/api/my-weekly-update/video",
        files={"video": (name, data, "video/mp4")},
        data={"consent": "true" if consent else "false"},
        headers=headers,
    )


@pytest.fixture
def team(client: TestClient):
    staff, project, lisa, tom = drone_team(client)
    set_settings(client, staff, WEDNESDAY_17)
    return staff, project, lisa, tom


def current_media(client: TestClient, headers: dict) -> list[dict]:
    return client.get("/api/my-weekly-update", headers=headers).json()["current"][
        "media"
    ]


def files_of(settings: Settings, project: int) -> list[str]:
    folder = settings.social_media_dir / str(project)
    return sorted(path.name for path in folder.iterdir()) if folder.exists() else []


def test_a_video_is_processed_into_two_copies(
    client: TestClient, team, settings: Settings, short_clip: bytes
):
    _, project, lisa, tom = team

    response = upload(client, lisa, short_clip)

    assert response.status_code == 200, response.text
    assert response.json()["current"]["media"][0]["state"] == "processing"
    # The test client returns after the background processing.
    [medium] = current_media(client, tom)
    assert medium["kind"] == "video"
    assert medium["state"] == "ready"
    assert (medium["width"], medium["height"]) == (640, 360)
    assert medium["seconds"] == pytest.approx(2, abs=0.2)
    assert files_of(settings, project) == [
        f"{medium['id']}.ai.mp4",
        f"{medium['id']}.mp4",
    ]
    served = client.get(f"/api/weekly-media/{medium['id']}", headers=tom)
    assert served.status_code == 200
    assert served.headers["content-type"] == "video/mp4"
    assert video.probe(settings.social_media_dir / str(project) / f"{medium['id']}.mp4")


def test_a_mov_video_is_accepted(client: TestClient, team, tmp_path: Path):
    _, _, lisa, _ = team
    response = upload(client, lisa, clip(tmp_path, container="mov"), name="clip.mov")
    assert response.status_code == 200, response.text
    assert current_media(client, lisa)[0]["state"] == "ready"


def test_nothing_uploads_without_the_consent_tick(
    client: TestClient, team, short_clip: bytes
):
    _, _, lisa, _ = team
    response = upload(client, lisa, short_clip, consent=False)
    assert response.status_code == 422
    assert "agrees" in response.json()["detail"]
    assert current_media(client, lisa) == []


def test_a_too_long_video_is_refused(client: TestClient, team, tmp_path: Path):
    _, _, lisa, _ = team
    response = upload(client, lisa, clip(tmp_path, seconds=95, size="160x120"))
    assert response.status_code == 422
    assert "95 seconds long" in response.json()["detail"]


def test_a_file_that_isnt_a_video_is_refused(client: TestClient, team):
    _, _, lisa, _ = team
    response = upload(client, lisa, b"definitely not a video")
    assert response.status_code == 422
    assert "isn't a video" in response.json()["detail"]


def test_a_too_large_video_is_refused(
    client: TestClient, team, short_clip: bytes, monkeypatch, settings: Settings
):
    _, _, lisa, _ = team
    monkeypatch.setattr(social, "MAX_VIDEO_BYTES", 1000)
    response = upload(client, lisa, short_clip)
    assert response.status_code == 422
    assert "larger than 200 MB" in response.json()["detail"]
    assert list((settings.social_media_dir / "incoming").iterdir()) == []


def test_one_video_per_week_removable_until_the_deadline(
    client: TestClient, team, settings: Settings, short_clip: bytes
):
    _, project, lisa, tom = team
    first = upload(client, lisa, short_clip).json()["current"]["media"][0]["id"]

    response = upload(client, tom, short_clip)
    assert response.status_code == 422
    assert "already has a video" in response.json()["detail"]

    removed = client.delete(f"/api/my-weekly-update/media/{first}", headers=tom)
    assert removed.status_code == 200
    assert files_of(settings, project) == []
    second = upload(client, tom, short_clip).json()["current"]["media"][0]["id"]

    close_the_open_week(project)
    response = client.delete(f"/api/my-weekly-update/media/{second}", headers=tom)
    assert response.status_code == 422


def test_a_video_that_cant_be_processed_shows_as_failed(
    client: TestClient, team, settings: Settings, short_clip: bytes, monkeypatch
):
    _, project, lisa, _ = team

    def broken(source, posted, for_ai):
        raise subprocess.CalledProcessError(1, "ffmpeg")

    monkeypatch.setattr(video, "encode", broken)
    medium = upload(client, lisa, short_clip).json()["current"]["media"][0]["id"]

    assert current_media(client, lisa)[0]["state"] == "failed"
    assert files_of(settings, project) == []
    assert client.get(f"/api/weekly-media/{medium}", headers=lisa).status_code == 404


def test_processing_resumes_after_a_restart(
    client: TestClient, team, settings: Settings, short_clip: bytes, monkeypatch
):
    _, project, lisa, _ = team
    # As if the backend stopped before processing the upload.
    monkeypatch.setattr(social, "process_video", lambda *args: None)
    upload(client, lisa, short_clip)
    assert current_media(client, lisa)[0]["state"] == "processing"
    monkeypatch.undo()

    social.resume_processing(client.app.state.sessionmaker, settings.social_media_dir)

    assert current_media(client, lisa)[0]["state"] == "ready"


def test_staff_see_how_full_the_disk_is(client: TestClient, team):
    staff, _, lisa, _ = team
    teacher = ready_to_work(client, "teacher")
    found = client.get("/api/social/storage", headers=teacher).json()
    assert 0 < found["used_share"] < 1
    assert found["warning"] == (found["used_share"] > 0.8)
    assert client.get("/api/social/storage", headers=lisa).status_code == 403
