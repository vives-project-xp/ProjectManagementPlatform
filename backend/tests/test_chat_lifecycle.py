from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from pmp_backend.services import chat
from pmp_backend.settings import Settings
from pmp_backend.testing import TEST_DATABASE_URL
from tests.conftest import add_member, create_project, ready_to_work
from tests.test_chat import logged_in_student, send, student_id
from tests.test_chat_files import JPG
from tests.test_chat_files import send as send_files
from tests.test_chat_typing_seen_search import typing


def archived_chat(client: TestClient) -> tuple[dict, dict, int, dict]:
    """A Teacher, a former Member, an Archived Project with one photo message,
    and that message."""
    teacher = ready_to_work(client, "teacher")
    drone = create_project(client, teacher, "Drone")
    add_member(client, teacher, drone, student_id(client, teacher))
    student = ready_to_work(client, "student")
    sent = send_files(
        client, student, drone, [("flight.jpg", JPG, "image/jpeg")], body="Hi"
    ).json()
    client.post(f"/api/projects/{drone}/archive", headers=teacher)
    return teacher, student, drone, sent


def move_archiving_back(project_id: int, days: int) -> None:
    """Pretend the Project was archived `days` ago (the database's clock)."""
    engine = create_engine(TEST_DATABASE_URL)
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE projects SET archived_at = now() - make_interval(days => :d) "
                "WHERE id = :id"
            ),
            {"d": days, "id": project_id},
        )
    engine.dispose()


def clean_up(client: TestClient, settings: Settings) -> list[int]:
    with client.app.state.sessionmaker() as session:
        return chat.clean_up(session, settings.chat_files_dir)


def test_an_archived_chat_is_read_only_for_staff_only(client: TestClient):
    teacher, student, drone, sent = archived_chat(client)

    shown = client.get(f"/api/projects/{drone}/chat", headers=teacher).json()

    assert shown["read_only"] is True
    assert shown["deleted_on"] == str(date.today() + timedelta(days=182))
    messages = client.get(f"/api/projects/{drone}/chat/messages", headers=teacher)
    assert [m["body"] for m in messages.json()] == ["Hi"]
    # The former Member (now a Maker) no longer reads it.
    refused = client.get(f"/api/projects/{drone}/chat/messages", headers=student)
    assert refused.status_code == 403
    for response in (
        send(client, teacher, drone, "Late"),
        client.put(
            f"/api/chat/messages/{sent['id']}",
            json={"body": "Changed"},
            headers=student,
        ),
        client.put(f"/api/chat/messages/{sent['id']}/reactions/👍", headers=teacher),
        typing(client, teacher, drone),
    ):
        assert response.status_code in (403, 409), response.text


def test_restoring_brings_the_chat_back_with_its_history(client: TestClient):
    teacher, _, drone, _ = archived_chat(client)

    client.post(f"/api/projects/{drone}/restore", headers=teacher)

    shown = client.get(f"/api/projects/{drone}/chat", headers=teacher).json()
    assert shown["read_only"] is False and shown["deleted_on"] is None
    assert send(client, teacher, drone, "We're back").status_code == 201
    bodies = client.get(f"/api/projects/{drone}/chat/messages", headers=teacher)
    assert [m["body"] for m in bodies.json()] == ["Hi", "We're back"]


def test_the_clean_up_deletes_chats_six_months_after_archiving(
    client: TestClient, settings: Settings
):
    teacher, _, drone, sent = archived_chat(client)
    robot = create_project(client, teacher, "Robot")
    send(client, teacher, robot, "Active chats stay")
    file_path = settings.chat_files_dir / str(drone) / str(sent["files"][0]["id"])
    assert file_path.is_file()

    move_archiving_back(drone, 181)
    assert clean_up(client, settings) == []
    move_archiving_back(drone, 183)
    assert clean_up(client, settings) == [drone]

    assert not file_path.exists()
    messages = client.get(f"/api/projects/{drone}/chat/messages", headers=teacher)
    assert messages.json() == []
    other = client.get(f"/api/projects/{robot}/chat/messages", headers=teacher)
    assert [m["body"] for m in other.json()] == ["Active chats stay"]
    # Nothing left to delete; a restore starts an empty chat.
    assert clean_up(client, settings) == []
    client.post(f"/api/projects/{drone}/restore", headers=teacher)
    assert send(client, teacher, drone, "Fresh start").status_code == 201


def test_deleting_a_user_keeps_their_messages_as_deleted_user(client: TestClient):
    teacher = ready_to_work(client, "teacher")
    superuser = ready_to_work(client, "superuser")
    drone = create_project(client, teacher, "Drone")
    lotte = logged_in_student(client, superuser, "Lotte")
    lotte_id = client.get("/api/auth/me", headers=lotte).json()["id"]
    client.post(
        f"/api/projects/{drone}/chat/guests",
        json={"user_id": lotte_id},
        headers=teacher,
    )
    written = send(client, lotte, drone, "Hello from Lotte").json()
    client.put(f"/api/chat/messages/{written['id']}/reactions/👍", headers=lotte)

    deleted = client.delete(f"/api/users/{lotte_id}", headers=superuser)

    assert deleted.status_code == 204, deleted.text
    shown = client.get(f"/api/projects/{drone}/chat/messages", headers=teacher).json()
    assert [(m["author"], m["body"]) for m in shown] == [(None, "Hello from Lotte")]
    assert shown[0]["reactions"] == []
