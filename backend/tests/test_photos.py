from fastapi.testclient import TestClient

from pmp_backend.settings import Settings
from tests.conftest import (
    add_member,
    create_project,
    ready_to_work,
)

JPG = b"\xff\xd8\xff\xe0" + b"jpg-body" * 10
PNG = b"\x89PNG\r\n\x1a\n" + b"png-body" * 10
FIVE_MB = 5 * 1024 * 1024


def upload(
    client: TestClient,
    headers: dict[str, str],
    project_id: int,
    data: bytes = JPG,
    content_type: str = "image/jpeg",
    name: str = "cover.jpg",
):
    return client.put(
        f"/api/projects/{project_id}/photo",
        files={"photo": (name, data, content_type)},
        headers=headers,
    )


def student_id(client: TestClient, headers: dict[str, str]) -> int:
    users = client.get("/api/users?role=student", headers=headers).json()
    return next(u["id"] for u in users if u["email"] == "student@pmp.local")


def test_teacher_uploads_and_gets_a_photo(client: TestClient):
    headers = ready_to_work(client, "teacher")
    project = create_project(client, headers, "Smart Greenhouse")

    response = upload(client, headers, project)

    assert response.status_code == 200, response.text
    assert response.json()["photo_version"] == 1
    photo = client.get(f"/api/projects/{project}/photo", headers=headers)
    assert photo.status_code == 200
    assert photo.content == JPG
    assert photo.headers["content-type"] == "image/jpeg"
    listed = client.get("/api/projects", headers=headers).json()
    assert listed[0]["photo_version"] == 1


def test_a_new_photo_replaces_the_old_one(client: TestClient):
    headers = ready_to_work(client, "superuser")
    project = create_project(client, headers, "Smart Greenhouse")
    upload(client, headers, project)

    response = upload(client, headers, project, PNG, "image/png", "cover.png")

    assert response.status_code == 200, response.text
    assert response.json()["photo_version"] == 2
    photo = client.get(f"/api/projects/{project}/photo", headers=headers)
    assert photo.content == PNG
    assert photo.headers["content-type"] == "image/png"


def test_teacher_removes_a_photo(client: TestClient):
    headers = ready_to_work(client, "teacher")
    project = create_project(client, headers, "Smart Greenhouse")
    upload(client, headers, project)

    response = client.delete(f"/api/projects/{project}/photo", headers=headers)

    assert response.status_code == 200, response.text
    assert response.json()["photo_version"] is None
    photo = client.get(f"/api/projects/{project}/photo", headers=headers)
    assert photo.status_code == 404
    assert photo.json()["detail"] == "Smart Greenhouse has no photo."


def test_a_project_without_photo_has_none(client: TestClient):
    headers = ready_to_work(client, "teacher")
    project = create_project(client, headers, "Smart Greenhouse")

    details = client.get(f"/api/projects/{project}", headers=headers).json()

    assert details["photo_version"] is None
    assert (
        client.get(f"/api/projects/{project}/photo", headers=headers).status_code == 404
    )


def test_only_real_jpg_or_png_is_accepted(client: TestClient):
    headers = ready_to_work(client, "teacher")
    project = create_project(client, headers, "Smart Greenhouse")

    renamed_text = upload(client, headers, project, b"not really a photo")
    gif = upload(client, headers, project, b"GIF89a" + b"x" * 20, "image/gif", "a.gif")
    wrong_type = upload(client, headers, project, PNG, "text/plain", "cover.png")

    for response in (renamed_text, gif, wrong_type):
        assert response.status_code == 422
        assert response.json()["detail"] == "Only JPG and PNG photos are accepted."
    details = client.get(f"/api/projects/{project}", headers=headers).json()
    assert details["photo_version"] is None


def test_photo_over_5_mb_is_refused(client: TestClient):
    headers = ready_to_work(client, "teacher")
    project = create_project(client, headers, "Smart Greenhouse")

    exactly = upload(client, headers, project, JPG[:4] + b"x" * (FIVE_MB - 4))
    too_big = upload(client, headers, project, JPG[:4] + b"x" * (FIVE_MB - 3))

    assert exactly.status_code == 200, exactly.text
    assert too_big.status_code == 422
    assert too_big.json()["detail"] == "The photo is larger than 5 MB."


def test_archived_project_keeps_its_photo_but_refuses_changes(client: TestClient):
    headers = ready_to_work(client, "teacher")
    project = create_project(client, headers, "Smart Greenhouse")
    upload(client, headers, project)
    client.post(f"/api/projects/{project}/archive", headers=headers)

    replace = upload(client, headers, project, PNG, "image/png")
    remove = client.delete(f"/api/projects/{project}/photo", headers=headers)

    assert replace.status_code == 409
    assert remove.status_code == 409
    assert "Restore it first" in replace.json()["detail"]
    photo = client.get(f"/api/projects/{project}/photo", headers=headers)
    assert photo.content == JPG


def test_deleting_a_project_deletes_its_photo(client: TestClient, settings: Settings):
    headers = ready_to_work(client, "teacher")
    project = create_project(client, headers, "Smart Greenhouse")
    upload(client, headers, project)

    response = client.delete(f"/api/projects/{project}", headers=headers)

    assert response.status_code == 204, response.text
    # Nothing is left behind in the photos volume (and so in the backups).
    assert list(settings.photos_dir.iterdir()) == []


def test_student_sees_only_their_own_projects_photo(client: TestClient):
    staff = ready_to_work(client, "superuser")
    own = create_project(client, staff, "Smart Greenhouse")
    other = create_project(client, staff, "Drone")
    add_member(client, staff, own, student_id(client, staff))
    upload(client, staff, own)
    upload(client, staff, other, PNG, "image/png")
    student = ready_to_work(client, "student")

    my_project = client.get("/api/my-project", headers=student).json()
    mine = client.get(f"/api/projects/{own}/photo", headers=student)
    theirs = client.get(f"/api/projects/{other}/photo", headers=student)

    assert my_project["id"] == own
    assert my_project["photo_version"] == 1
    assert mine.status_code == 200
    assert mine.content == JPG
    assert theirs.status_code == 403


def test_students_cannot_change_photos(client: TestClient):
    staff = ready_to_work(client, "teacher")
    project = create_project(client, staff, "Smart Greenhouse")
    student = ready_to_work(client, "student")

    assert upload(client, student, project).status_code == 403
    assert (
        client.delete(f"/api/projects/{project}/photo", headers=student).status_code
        == 403
    )


def test_unknown_project_has_no_photo(client: TestClient):
    headers = ready_to_work(client, "teacher")

    assert upload(client, headers, 9999).status_code == 404
    assert client.get("/api/projects/9999/photo", headers=headers).status_code == 404
