import io
import random
from pathlib import Path

import pillow_heif
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

from pmp_backend.settings import Settings
from tests.conftest import ready_to_work
from tests.test_weekly_updates import (
    WEDNESDAY_17,
    close_the_open_week,
    drone_team,
    logged_in_student,
    set_settings,
)

GPS_TAG = 0x8825
ORIENTATION_TAG = 0x0112


def scene(width: int = 1600, height: int = 1200, seed: int = 1) -> Image.Image:
    """A sharp, evenly lit picture: lots of shapes with crisp edges."""
    shuffle = random.Random(seed)
    image = Image.new("RGB", (width, height), (120, 130, 140))
    draw = ImageDraw.Draw(image)
    for _ in range(400):
        x, y = shuffle.randrange(width), shuffle.randrange(height)
        size = shuffle.randrange(10, 120)
        colour = tuple(shuffle.randrange(30, 220) for _ in range(3))
        draw.rectangle((x, y, x + size, y + size // 2), fill=colour)
    return image


def jpeg(image: Image.Image, **options) -> bytes:
    out = io.BytesIO()
    image.save(out, "JPEG", quality=92, **options)
    return out.getvalue()


SHARP = jpeg(scene())


def upload(client: TestClient, headers: dict, data: bytes = SHARP, *, consent=True):
    return client.post(
        "/api/my-weekly-update/photos",
        files={"photo": ("photo.jpg", data, "image/jpeg")},
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


def stored(client: TestClient, headers: dict, medium_id: int) -> Image.Image:
    response = client.get(f"/api/weekly-media/{medium_id}", headers=headers)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "image/jpeg"
    return Image.open(io.BytesIO(response.content))


def test_a_member_uploads_a_photo_the_team_sees(client: TestClient, team):
    _, _, lisa, tom = team

    response = upload(client, lisa)

    assert response.status_code == 200, response.text
    [photo] = response.json()["current"]["media"]
    assert photo["kind"] == "photo"
    assert photo["uploaded_by"] == "Lisa Peeters"
    assert (photo["width"], photo["height"]) == (1600, 1200)
    assert [m["id"] for m in current_media(client, tom)] == [photo["id"]]
    assert stored(client, tom, photo["id"]).size == (1600, 1200)


def test_nothing_uploads_without_the_consent_tick(client: TestClient, team):
    _, _, lisa, _ = team
    response = upload(client, lisa, consent=False)
    assert response.status_code == 422
    assert "agrees" in response.json()["detail"]
    assert current_media(client, lisa) == []


@pytest.mark.parametrize(
    ("photo", "reason"),
    [
        (jpeg(scene().filter(ImageFilter.GaussianBlur(8))), "blurry"),
        (jpeg(ImageEnhance.Brightness(scene()).enhance(0.15)), "too dark"),
        (jpeg(Image.new("RGB", (1600, 1200), (252, 252, 252))), "overexposed"),
        (jpeg(scene(1000, 800)), "too small"),
        (b"not a photo at all", "isn't a photo"),
    ],
    ids=["blurry", "dark", "overexposed", "small", "not-a-photo"],
)
def test_the_quality_check_refuses_with_a_reason(
    client: TestClient, team, photo: bytes, reason: str
):
    _, _, lisa, _ = team
    response = upload(client, lisa, photo)
    assert response.status_code == 422
    assert reason in response.json()["detail"]
    assert current_media(client, lisa) == []


def test_at_most_five_photos_and_refused_ones_dont_count(client: TestClient, team):
    _, _, lisa, tom = team
    upload(client, lisa, jpeg(scene().filter(ImageFilter.GaussianBlur(8))))
    for seed in range(5):
        assert upload(client, lisa, jpeg(scene(seed=seed))).status_code == 200

    response = upload(client, tom)

    assert response.status_code == 422
    assert "already has 5 photos" in response.json()["detail"]


def test_photos_are_stored_small_upright_and_without_location(client: TestClient, team):
    _, _, lisa, _ = team
    big = scene(4000, 3000)
    exif = Image.Exif()
    # Taken with the phone turned: shown rotated by 90°.
    exif[ORIENTATION_TAG] = 6
    exif[GPS_TAG] = {1: "N", 2: (51.0, 12.0, 30.0)}
    response = upload(client, lisa, jpeg(big, exif=exif.tobytes()))

    assert response.status_code == 200, response.text
    [photo] = response.json()["current"]["media"]
    kept = stored(client, lisa, photo["id"])
    assert kept.size == (1620, 2160)
    assert dict(kept.getexif()) == {}


def test_heic_photos_are_accepted(client: TestClient, team):
    _, _, lisa, _ = team
    out = io.BytesIO()
    pillow_heif.from_pillow(scene()).save(out, quality=90)

    response = upload(client, lisa, out.getvalue())

    assert response.status_code == 200, response.text
    assert stored(client, lisa, response.json()["current"]["media"][0]["id"]).size == (
        1600,
        1200,
    )


def test_a_too_large_file_is_refused(client: TestClient, team):
    _, _, lisa, _ = team
    response = upload(client, lisa, SHARP + b"\0" * (15 * 1024 * 1024))
    assert response.status_code == 422
    assert "larger than 15 MB" in response.json()["detail"]


def test_members_remove_photos_until_the_deadline(
    client: TestClient, team, settings: Settings
):
    _, project, lisa, tom = team
    first = upload(client, lisa).json()["current"]["media"][0]["id"]
    second = upload(client, lisa, jpeg(scene(seed=2))).json()["current"]["media"][1]

    response = client.delete(f"/api/my-weekly-update/media/{first}", headers=tom)

    assert response.status_code == 200, response.text
    assert [m["id"] for m in response.json()["current"]["media"]] == [second["id"]]
    assert not (settings.social_media_dir / str(project) / f"{first}.jpg").exists()

    close_the_open_week(project)
    response = client.delete(f"/api/my-weekly-update/media/{second['id']}", headers=tom)
    assert response.status_code == 422
    assert "locked" in response.json()["detail"]
    earlier = client.get("/api/my-weekly-update", headers=tom).json()["earlier"]
    assert [m["id"] for m in earlier[0]["media"]] == [second["id"]]


def test_only_the_team_and_staff_see_the_photos(client: TestClient, team):
    staff, _, lisa, _ = team
    photo = upload(client, lisa).json()["current"]["media"][0]["id"]
    _, outsider = logged_in_student(client, staff, "Mia")
    teacher = ready_to_work(client, "teacher")

    assert client.get(f"/api/weekly-media/{photo}", headers=outsider).status_code == 403
    assert client.get(f"/api/weekly-media/{photo}", headers=teacher).status_code == 200
    assert client.get("/api/weekly-media/999", headers=teacher).status_code == 404
    response = client.delete(f"/api/my-weekly-update/media/{photo}", headers=outsider)
    assert response.status_code == 404


def test_staff_see_the_photos_on_the_project(client: TestClient, team):
    staff, project, lisa, _ = team
    upload(client, lisa)
    weeks = client.get(f"/api/projects/{project}/weekly-updates", headers=staff).json()
    assert [m["uploaded_by"] for m in weeks[0]["media"]] == ["Lisa Peeters"]


def test_a_deleted_uploader_shows_as_deleted_user(client: TestClient, team):
    staff, project, lisa, _ = team
    upload(client, lisa)
    lisa_id = client.get("/api/auth/me", headers=lisa).json()["id"]
    client.delete(f"/api/projects/{project}/members/{lisa_id}", headers=staff)

    assert client.delete(f"/api/users/{lisa_id}", headers=staff).status_code == 204

    weeks = client.get(f"/api/projects/{project}/weekly-updates", headers=staff).json()
    assert weeks[0]["media"][0]["uploaded_by"] == "Deleted user"


def test_deleting_a_project_deletes_its_photos(client: TestClient, settings: Settings):
    staff = ready_to_work(client, "superuser")
    set_settings(client, staff, WEDNESDAY_17)
    project = client.post(
        "/api/projects",
        json={
            "title": "Drone",
            "product_owner_id": next(
                t["id"]
                for t in client.get("/api/teachers", headers=staff).json()
                if t["name"] == "Teacher Account"
            ),
            "team_size_min": 1,
            "team_size_max": 3,
        },
        headers=staff,
    ).json()["id"]
    student, lisa = logged_in_student(client, staff, "Lisa")
    client.post(
        f"/api/projects/{project}/members",
        json={"student_id": student, "confirm_move": False},
        headers=staff,
    )
    upload(client, lisa)
    folder: Path = settings.social_media_dir / str(project)
    assert any(folder.iterdir())
    client.delete(f"/api/projects/{project}/members/{student}", headers=staff)

    assert client.delete(f"/api/projects/{project}", headers=staff).status_code == 204
    assert not folder.exists()
