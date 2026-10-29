from fastapi.testclient import TestClient

from pmp_backend.settings import Settings
from tests.conftest import add_member, create_project, ready_to_work
from tests.test_chat import logged_in_student, student_id

JPG = b"\xff\xd8\xff\xe0" + b"jpg-body" * 10
PDF = b"%PDF-1.7 report"
TEN_MB = 10 * 1024 * 1024


def send(client: TestClient, headers, project_id: int, files, body: str = ""):
    return client.post(
        f"/api/projects/{project_id}/chat/messages",
        data={"body": body},
        files=[("files", file) for file in files],
        headers=headers,
    )


def team_chat(client: TestClient) -> tuple[dict, dict, int]:
    """A Teacher, a Member and their Project's id."""
    teacher = ready_to_work(client, "teacher")
    drone = create_project(client, teacher, "Drone")
    add_member(client, teacher, drone, student_id(client, teacher))
    return teacher, ready_to_work(client, "student"), drone


def test_photos_and_files_are_sent_and_downloaded(client: TestClient):
    teacher, student, drone = team_chat(client)

    response = send(
        client,
        student,
        drone,
        [("drone.jpg", JPG, "image/jpeg"), ("report.pdf", PDF, "application/pdf")],
        body="Our first flight",
    )

    assert response.status_code == 201, response.text
    message = response.json()
    assert message["body"] == "Our first flight"
    photo, report = message["files"]
    assert {key: photo[key] for key in ("name", "size", "is_image")} == {
        "name": "drone.jpg",
        "size": len(JPG),
        "is_image": True,
    }
    assert report["name"] == "report.pdf" and report["is_image"] is False
    listed = client.get(f"/api/projects/{drone}/chat/messages", headers=teacher)
    assert listed.json()[0]["files"] == message["files"]

    shown = client.get(f"/api/chat-files/{photo['id']}", headers=teacher)
    assert shown.status_code == 200
    assert shown.content == JPG
    assert shown.headers["content-type"] == "image/jpeg"
    assert shown.headers["content-disposition"].startswith("inline")
    download = client.get(f"/api/chat-files/{report['id']}", headers=teacher)
    assert download.content == PDF
    assert download.headers["content-type"] == "application/octet-stream"
    assert download.headers["content-disposition"] == (
        "attachment; filename*=UTF-8''report.pdf"
    )


def test_a_message_can_be_files_only(client: TestClient):
    teacher, _, drone = team_chat(client)

    response = send(client, teacher, drone, [("plan.txt", b"step 1", "text/plain")])

    assert response.status_code == 201
    assert response.json()["body"] == ""
    empty = send(client, teacher, drone, [], body="  ")
    assert empty.status_code == 422
    assert empty.json()["detail"] == "Write a message or attach a file first."


def test_limits_on_number_and_size(client: TestClient):
    teacher, _, drone = team_chat(client)
    six = [(f"{n}.txt", b"x", "text/plain") for n in range(6)]

    too_many = send(client, teacher, drone, six)
    too_large = send(
        client, teacher, drone, [("big.zip", b"x" * (TEN_MB + 1), "application/zip")]
    )
    just_right = send(
        client, teacher, drone, [("max.zip", b"x" * TEN_MB, "application/zip")]
    )

    assert too_many.status_code == 422
    assert too_many.json()["detail"] == "A message can have at most 5 photos or files."
    assert too_large.status_code == 422
    assert too_large.json()["detail"] == "big.zip is larger than 10 MB."
    assert just_right.status_code == 201
    assert send(client, teacher, drone, six[:5]).status_code == 201


def test_programs_are_refused(client: TestClient):
    teacher, _, drone = team_chat(client)

    for name, data in [
        ("setup.exe", b"anything"),
        ("run.BAT", b"echo hi"),
        ("deploy.sh", b"#!/bin/sh"),
        ("app.apk", b"PK"),
        # A program under another name.
        ("holiday.jpg", b"MZ\x90\x00"),
    ]:
        response = send(client, teacher, drone, [(name, data, "image/jpeg")])
        assert response.status_code == 422, name
        assert response.json()["detail"] == (
            f"{name} is a program, and programs can't be sent."
        )
    assert (
        client.get(f"/api/projects/{drone}/chat/messages", headers=teacher).json() == []
    )


def test_only_a_real_photo_is_shown_as_one(client: TestClient):
    teacher, _, drone = team_chat(client)

    fake = send(client, teacher, drone, [("page.png", b"<html>", "image/png")])
    file = fake.json()["files"][0]

    assert file["is_image"] is False
    response = client.get(f"/api/chat-files/{file['id']}", headers=teacher)
    assert response.headers["content-disposition"].startswith("attachment")


def test_the_uploaded_name_never_picks_the_folder(
    client: TestClient, settings: Settings
):
    teacher, _, drone = team_chat(client)

    response = send(client, teacher, drone, [("../../evil.txt", b"x", "text/plain")])

    file = response.json()["files"][0]
    assert file["name"] == "evil.txt"
    stored = sorted(
        p.relative_to(settings.chat_files_dir).as_posix()
        for p in settings.chat_files_dir.rglob("*")
        if p.is_file()
    )
    assert stored == [f"{drone}/{file['id']}"]


def test_only_who_can_read_the_chat_gets_its_files(client: TestClient):
    teacher, student, drone = team_chat(client)
    superuser = ready_to_work(client, "superuser")
    outsider = logged_in_student(client, superuser, "Lotte")
    file = send(client, student, drone, [("drone.jpg", JPG, "image/jpeg")]).json()[
        "files"
    ][0]

    assert (
        client.get(f"/api/chat-files/{file['id']}", headers=superuser).status_code
        == 200
    )
    refused = client.get(f"/api/chat-files/{file['id']}", headers=outsider)
    assert refused.status_code == 403
    assert client.get("/api/chat-files/999999", headers=teacher).status_code == 404
    assert client.get(f"/api/chat-files/{file['id']}").status_code == 401


def test_an_archived_chat_takes_no_files(client: TestClient):
    teacher, _, drone = team_chat(client)
    client.post(f"/api/projects/{drone}/archive", headers=teacher)

    response = send(client, teacher, drone, [("a.txt", b"x", "text/plain")])

    assert response.status_code == 409


def test_deleting_a_project_deletes_its_chat_files(
    client: TestClient, settings: Settings
):
    teacher = ready_to_work(client, "teacher")
    drone = create_project(client, teacher, "Drone")
    send(client, teacher, drone, [("a.txt", b"x", "text/plain")])
    assert (settings.chat_files_dir / str(drone)).is_dir()

    response = client.delete(f"/api/projects/{drone}", headers=teacher)

    assert response.status_code == 204
    assert not (settings.chat_files_dir / str(drone)).exists()
