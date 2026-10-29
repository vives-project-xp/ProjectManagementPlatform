from fastapi.testclient import TestClient

from tests.conftest import add_member, create_student, ready_to_work
from tests.test_chat import logged_in_student, send, unread
from tests.test_chat_edit_delete import delete, edit, messages, team_chat


def react(client: TestClient, headers, message_id: int, emoji: str, on=True):
    url = f"/api/chat/messages/{message_id}/reactions/{emoji}"
    return (client.put if on else client.delete)(url, headers=headers)


def chat_list(client: TestClient, headers) -> list:
    return client.get("/api/chats", headers=headers).json()


def test_reactions_count_with_names(client: TestClient):
    teacher, student, drone = team_chat(client)
    sent = send(client, student, drone, "We flew!").json()

    react(client, teacher, sent["id"], "🎉")
    react(client, student, sent["id"], "🎉")
    react(client, student, sent["id"], "👍")
    again = react(client, student, sent["id"], "👍")

    assert again.status_code == 200, again.text
    assert again.json()["reactions"] == [
        {"emoji": "👍", "count": 1, "names": ["Student Account"], "mine": True},
        {
            "emoji": "🎉",
            "count": 2,
            "names": ["Teacher Account", "Student Account"],
            "mine": True,
        },
    ]
    # Open chats get reactions with the next poll.
    changed = messages(client, teacher, drone, since=sent["revision"])
    assert [r["emoji"] for r in changed[0]["reactions"]] == ["👍", "🎉"]
    assert changed[0]["reactions"][0]["mine"] is False

    taken_back = react(client, student, sent["id"], "🎉", on=False)
    assert [(r["emoji"], r["count"]) for r in taken_back.json()["reactions"]] == [
        ("👍", 1),
        ("🎉", 1),
    ]


def test_only_the_six_reactions_and_only_on_live_messages(client: TestClient):
    teacher, student, drone = team_chat(client)
    outsider = logged_in_student(client, ready_to_work(client, "superuser"), "Lotte")
    sent = send(client, student, drone, "Hello").json()

    other = react(client, teacher, sent["id"], "🍕")
    assert other.status_code == 422
    assert other.json()["detail"] == "React with 👍 ❤️ 😂 😮 😢 🎉 only."
    assert react(client, outsider, sent["id"], "👍").status_code == 403
    react(client, teacher, sent["id"], "❤️")
    delete(client, student, sent["id"])
    assert react(client, teacher, sent["id"], "👍").status_code == 409
    assert messages(client, teacher, drone)[0]["reactions"] == []


def test_mentions_mark_the_chat_until_read(client: TestClient):
    teacher, student, drone = team_chat(client)

    sent = send(client, student, drone, "@Teacher Account can you check this?")

    assert sent.json()["mentions_me"] is False
    assert messages(client, teacher, drone)[0]["mentions_me"] is True
    assert unread(client, teacher) == {"count": 1, "has_chat": True, "mentioned": True}
    assert chat_list(client, teacher)[0]["mentioned"] is True
    # A message without a mention keeps the marker off for others.
    assert unread(client, student)["mentioned"] is False

    client.post(
        f"/api/projects/{drone}/chat/read",
        json={"message_id": sent.json()["id"]},
        headers=teacher,
    )
    assert unread(client, teacher)["mentioned"] is False


def test_at_team_mentions_every_member(client: TestClient):
    teacher, student, drone = team_chat(client)
    superuser = ready_to_work(client, "superuser")
    other = create_student(client, superuser, "Lotte")
    add_member(client, teacher, drone, other)

    send(client, teacher, drone, "Deadline tomorrow, @team!")

    assert messages(client, student, drone)[0]["mentions_me"] is True
    assert unread(client, student)["mentioned"] is True
    # The Product Owner wrote it; the Superuser only reads along.
    assert messages(client, superuser, drone)[0]["mentions_me"] is False


def test_staff_who_only_read_along_cannot_be_mentioned(client: TestClient):
    teacher, student, drone = team_chat(client)
    superuser = ready_to_work(client, "superuser")

    send(client, student, drone, "@Superuser Account look")

    assert messages(client, superuser, drone)[0]["mentions_me"] is False
    assert unread(client, superuser)["mentioned"] is False


def test_an_edit_changes_who_is_mentioned(client: TestClient):
    teacher, student, drone = team_chat(client)
    sent = send(client, student, drone, "Hi all").json()

    edit(client, student, sent["id"], "Hi @teacher account")
    assert messages(client, teacher, drone)[0]["mentions_me"] is True

    edit(client, student, sent["id"], "Hi all")
    assert messages(client, teacher, drone)[0]["mentions_me"] is False
    assert unread(client, teacher)["mentioned"] is False


def test_a_deleted_message_mentions_nobody(client: TestClient):
    teacher, student, drone = team_chat(client)
    sent = send(client, student, drone, "@Teacher Account look").json()

    delete(client, student, sent["id"])

    assert unread(client, teacher)["mentioned"] is False
    assert messages(client, teacher, drone)[0]["mentions_me"] is False
