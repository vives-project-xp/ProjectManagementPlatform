from fastapi.testclient import TestClient

from pmp_backend.settings import Settings
from tests.conftest import add_member, create_project, ready_to_work
from tests.test_chat import logged_in_student, send, student_id, unread
from tests.test_chat_files import JPG
from tests.test_chat_files import send as send_files


def team_chat(client: TestClient) -> tuple[dict, dict, int]:
    """A Teacher, a Member and their Project's id."""
    teacher = ready_to_work(client, "teacher")
    drone = create_project(client, teacher, "Drone")
    add_member(client, teacher, drone, student_id(client, teacher))
    return teacher, ready_to_work(client, "student"), drone


def edit(client: TestClient, headers, message_id: int, body: str):
    return client.put(
        f"/api/chat/messages/{message_id}", json={"body": body}, headers=headers
    )


def delete(client: TestClient, headers, message_id: int):
    return client.delete(f"/api/chat/messages/{message_id}", headers=headers)


def messages(client: TestClient, headers, project_id: int, since=None) -> list:
    params = {} if since is None else {"since": since}
    response = client.get(
        f"/api/projects/{project_id}/chat/messages", params=params, headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json()


def reply(client: TestClient, headers, project_id: int, reply_to_id: int, body: str):
    return client.post(
        f"/api/projects/{project_id}/chat/messages",
        data={"body": body, "reply_to_id": str(reply_to_id)},
        headers=headers,
    )


def test_you_edit_your_own_message(client: TestClient):
    teacher, student, drone = team_chat(client)
    sent = send(client, student, drone, "Meeting at 10").json()
    assert sent["edited"] is False and sent["can_edit"] is True

    edited = edit(client, student, sent["id"], "  Meeting at 11  ")

    assert edited.status_code == 200, edited.text
    assert edited.json()["body"] == "Meeting at 11"
    assert edited.json()["edited"] is True
    # An open chat gets the edit with its next poll.
    changed = messages(client, teacher, drone, since=sent["revision"])
    assert [(m["id"], m["body"], m["edited"]) for m in changed] == [
        (sent["id"], "Meeting at 11", True)
    ]
    assert changed[0]["can_edit"] is False


def test_nobody_edits_someone_elses_message(client: TestClient):
    teacher, student, drone = team_chat(client)
    sent = send(client, student, drone, "Meeting at 10").json()

    refused = edit(client, teacher, sent["id"], "Changed by the teacher")

    assert refused.status_code == 403
    assert refused.json()["detail"] == "You can only edit your own messages."
    assert edit(client, student, sent["id"], "   ").status_code == 422
    assert edit(client, student, sent["id"], "x" * 4001).status_code == 422
    assert messages(client, teacher, drone)[0]["body"] == "Meeting at 10"


def test_you_delete_your_own_message_and_its_files(
    client: TestClient, settings: Settings
):
    teacher, student, drone = team_chat(client)
    sent = send_files(
        client, student, drone, [("drone.jpg", JPG, "image/jpeg")], body="Look"
    ).json()
    file_id = sent["files"][0]["id"]

    response = delete(client, student, sent["id"])

    assert response.status_code == 204
    changed = messages(client, teacher, drone, since=sent["revision"])
    assert [
        (m["body"], m["files"], m["deleted"], m["can_delete"]) for m in changed
    ] == [("", [], True, False)]
    assert client.get(f"/api/chat-files/{file_id}", headers=teacher).status_code == 404
    assert not (settings.chat_files_dir / str(drone) / str(file_id)).exists()
    # A deleted message is never Unread.
    assert unread(client, teacher)["count"] == 0
    again = delete(client, student, sent["id"])
    assert again.status_code == 409
    assert edit(client, student, sent["id"], "Back").status_code == 409


def test_staff_delete_any_message_but_students_only_their_own(client: TestClient):
    teacher, student, drone = team_chat(client)
    superuser = ready_to_work(client, "superuser")
    by_teacher = send(client, teacher, drone, "From the teacher").json()
    by_student = send(client, student, drone, "Something rude").json()
    assert by_student["can_delete"] is True
    assert messages(client, student, drone)[0]["can_delete"] is False

    refused = delete(client, student, by_teacher["id"])
    by_superuser = delete(client, superuser, by_student["id"])
    by_teacher_too = delete(client, teacher, by_teacher["id"])

    assert refused.status_code == 403
    assert refused.json()["detail"] == "You can only delete your own messages."
    assert by_superuser.status_code == 204
    assert by_teacher_too.status_code == 204
    assert [m["deleted"] for m in messages(client, student, drone)] == [True, True]


def test_outsiders_and_archived_chats(client: TestClient):
    teacher, student, drone = team_chat(client)
    outsider = logged_in_student(client, ready_to_work(client, "superuser"), "Lotte")
    sent = send(client, student, drone, "Hello").json()

    assert delete(client, outsider, sent["id"]).status_code == 403
    assert delete(client, teacher, 999999).status_code == 404
    client.post(f"/api/projects/{drone}/archive", headers=teacher)
    assert delete(client, teacher, sent["id"]).status_code == 409


def test_a_reply_quotes_the_original(client: TestClient):
    teacher, student, drone = team_chat(client)
    question = send(client, student, drone, "Who brings the drone?\nAnd the charger?")
    question = question.json()

    answer = reply(client, teacher, drone, question["id"], "I do")

    assert answer.status_code == 201, answer.text
    assert answer.json()["reply_to"] == {
        "id": question["id"],
        "author_name": "Student Account",
        "first_line": "Who brings the drone?",
        "deleted": False,
    }
    assert messages(client, student, drone)[1]["reply_to"]["id"] == question["id"]
    assert send(client, student, drone, "No reply").json()["reply_to"] is None


def test_a_quote_of_a_deleted_message_says_so(client: TestClient):
    teacher, student, drone = team_chat(client)
    question = send(client, student, drone, "Secret plan").json()
    answer = reply(client, teacher, drone, question["id"], "Nice").json()

    delete(client, student, question["id"])

    # The reply changes too, so open chats update its quote.
    changed = messages(client, teacher, drone, since=answer["revision"])
    quote = next(m for m in changed if m["id"] == answer["id"])["reply_to"]
    assert quote == {
        "id": question["id"],
        "author_name": "Student Account",
        "first_line": "",
        "deleted": True,
    }
    refused = reply(client, teacher, drone, question["id"], "Too late")
    assert refused.status_code == 422
    assert refused.json()["detail"] == (
        "This message was deleted, so you can't reply to it."
    )


def test_replies_stay_in_the_same_chat(client: TestClient):
    teacher, _, drone = team_chat(client)
    robot = create_project(client, teacher, "Robot")
    elsewhere = send(client, teacher, robot, "In another chat").json()

    response = reply(client, teacher, drone, elsewhere["id"], "Hi")

    assert response.status_code == 422
    assert response.json()["detail"] == "You can only reply to a message in this chat."
