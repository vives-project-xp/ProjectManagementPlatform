from fastapi.testclient import TestClient

from pmp_backend.services.chat import TypingBoard
from tests.conftest import ready_to_work
from tests.test_chat import logged_in_student, send
from tests.test_chat_edit_delete import delete, team_chat
from tests.test_chat_files import send as send_files
from tests.test_login_lockout import FakeClock


def updates(client: TestClient, headers, project_id: int, since: int = 0) -> dict:
    response = client.get(
        f"/api/projects/{project_id}/chat/updates",
        params={"since": since},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


def typing(client: TestClient, headers, project_id: int):
    return client.post(f"/api/projects/{project_id}/chat/typing", headers=headers)


def read(client: TestClient, headers, project_id: int, message_id: int) -> None:
    client.post(
        f"/api/projects/{project_id}/chat/read",
        json={"message_id": message_id},
        headers=headers,
    )


def search(client: TestClient, headers, project_id: int, **params):
    return client.get(
        f"/api/projects/{project_id}/chat/search", params=params, headers=headers
    )


def test_others_see_who_is_typing_for_five_seconds(client: TestClient):
    clock = FakeClock()
    client.app.state.chat_typing = TypingBoard(clock=clock)
    teacher, student, drone = team_chat(client)

    assert typing(client, student, drone).status_code == 204

    assert updates(client, teacher, drone)["typing"] == ["Student"]
    # Never yourself.
    assert updates(client, student, drone)["typing"] == []
    clock.now += 5.1
    assert updates(client, teacher, drone)["typing"] == []


def test_sending_ends_typing_and_staff_reading_along_never_type(client: TestClient):
    client.app.state.chat_typing = TypingBoard(clock=FakeClock())
    teacher, student, drone = team_chat(client)
    superuser = ready_to_work(client, "superuser")

    typing(client, student, drone)
    typing(client, superuser, drone)
    send(client, student, drone, "Done")

    assert updates(client, teacher, drone)["typing"] == []


def test_seen_by_counts_the_chat_people_who_read_it(client: TestClient):
    teacher, student, drone = team_chat(client)
    superuser = ready_to_work(client, "superuser")
    first = send(client, student, drone, "First").json()
    second = send(client, student, drone, "Second").json()
    assert second["seen_by"] == []

    read(client, teacher, drone, first["id"])
    # The Superuser only reads along: never in "Seen by".
    read(client, superuser, drone, second["id"])

    shown = updates(client, student, drone)
    assert [m["seen_by"] for m in shown["messages"]] == [["Teacher Account"], []]
    assert shown["reads"] == [{"name": "Teacher Account", "last_read_id": first["id"]}]
    # Only on your own messages.
    assert [m["seen_by"] for m in updates(client, teacher, drone)["messages"]] == [
        None,
        None,
    ]


def test_search_text_and_file_names_with_filters(client: TestClient):
    teacher, student, drone = team_chat(client)
    send(client, teacher, drone, "The 50% budget_plan is ready")
    send(client, student, drone, "Where is the BUDGET?")
    send_files(client, student, drone, [("budget.xlsx", b"x", "text/plain")])
    gone = send(client, student, drone, "budget secret").json()
    delete(client, student, gone["id"])
    student_user = client.get("/api/auth/me", headers=student).json()

    def bodies(**params) -> list[str]:
        response = search(client, teacher, drone, **params)
        assert response.status_code == 200, response.text
        return [m["body"] or m["files"][0]["name"] for m in response.json()]

    assert bodies(q="budget") == [
        "budget.xlsx",
        "Where is the BUDGET?",
        "The 50% budget_plan is ready",
    ]
    assert bodies(q="50%") == ["The 50% budget_plan is ready"]
    # % and _ are searched for as they are, not as wildcards.
    assert bodies(q="t%p") == []
    assert bodies(q="budget", files_only="true") == ["budget.xlsx"]
    assert len(bodies(**{"from": str(student_user["id"])})) == 2


def test_search_needs_something_and_access(client: TestClient):
    teacher, student, drone = team_chat(client)

    empty = search(client, teacher, drone, q="  ")

    assert empty.status_code == 422
    assert empty.json()["detail"] == "Type something to search for."
    outsider = logged_in_student(client, ready_to_work(client, "superuser"), "Lotte")
    assert search(client, outsider, drone, q="x").status_code == 403
