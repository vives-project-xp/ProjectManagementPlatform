import re

import pytest
from fastapi.testclient import TestClient

from tests.conftest import ready_to_work

READABLE = re.compile(r"^[A-HJ-NP-Za-km-z2-9-]{12,}$")
NEW_TEACHER = {
    "role": "teacher",
    "first_name": "Ann",
    "last_name": "Janssens",
    "email": "ann.janssens@vives.be",
}


def log_in(client: TestClient, email: str, password: str):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def import_csv(
    client: TestClient,
    headers,
    content: str | bytes,
    role: str = "student",
    programme: str | None = "Electronics-ICT",
    year: str | None = "2",
):
    data = {"role": role}
    if programme:
        data["programme"] = programme
    if year:
        data["year"] = year
    if isinstance(content, str):
        content = content.encode("utf-8")
    return client.post(
        "/api/users/import",
        files={"file": ("users.csv", content, "text/csv")},
        data=data,
        headers=headers,
    )


# Generated Temporary passwords


def test_creating_a_user_generates_a_temporary_password(client: TestClient):
    headers = ready_to_work(client, "superuser")

    first = client.post("/api/users", json=NEW_TEACHER, headers=headers).json()
    second = client.post(
        "/api/users",
        json=NEW_TEACHER | {"email": "bert@vives.be", "first_name": "Bert"},
        headers=headers,
    ).json()

    assert READABLE.match(first["temporary_password"])
    assert first["temporary_password"] != second["temporary_password"]
    login = log_in(client, "ann.janssens@vives.be", first["temporary_password"])
    assert login.status_code == 200
    assert login.json()["user"]["must_change_password"] is True


def test_a_typed_password_is_ignored(client: TestClient):
    headers = ready_to_work(client, "superuser")

    created = client.post(
        "/api/users",
        json=NEW_TEACHER | {"temporary_password": "typed-by-hand"},
        headers=headers,
    ).json()

    assert created["temporary_password"] != "typed-by-hand"
    assert log_in(client, "ann.janssens@vives.be", "typed-by-hand").status_code == 401


def test_reset_generates_a_new_temporary_password(client: TestClient):
    headers = ready_to_work(client, "superuser")
    created = client.post("/api/users", json=NEW_TEACHER, headers=headers).json()

    response = client.post(
        f"/api/users/{created['id']}/reset-password", headers=headers
    )

    assert response.status_code == 200, response.text
    new = response.json()["temporary_password"]
    assert READABLE.match(new)
    assert new != created["temporary_password"]
    old_login = log_in(client, NEW_TEACHER["email"], created["temporary_password"])
    assert old_login.status_code == 401
    assert log_in(client, NEW_TEACHER["email"], new).status_code == 200


# Importing


def test_import_creates_students_with_their_own_passwords(client: TestClient):
    headers = ready_to_work(client, "superuser")
    content = (
        "Firstname,Lastname,email\n"
        "Lisa,Peeters,Lisa.Peeters@student.vives.be\n"
        "Bram,Claes,bram.claes@student.vives.be\n"
    )

    response = import_csv(client, headers, content)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["skipped"] == []
    assert [(u["first_name"], u["email"]) for u in body["created"]] == [
        ("Lisa", "lisa.peeters@student.vives.be"),
        ("Bram", "bram.claes@student.vives.be"),
    ]
    passwords = [u["temporary_password"] for u in body["created"]]
    assert len(set(passwords)) == 2
    login = log_in(client, "lisa.peeters@student.vives.be", passwords[0])
    assert login.json()["user"]["programme"] == "Electronics-ICT"
    assert login.json()["user"]["year"] == "2"
    assert login.json()["user"]["must_change_password"] is True


def test_import_reads_semicolons_and_a_bom(client: TestClient):
    headers = ready_to_work(client, "superuser")
    content = "﻿Voornaam;Achternaam;E-mail\r\nAnn;Janssens;ann@vives.be\r\n"

    response = import_csv(client, headers, content, "teacher", None, None)

    assert response.status_code == 200, response.text
    created = response.json()["created"]
    assert [(u["last_name"], u["email"]) for u in created] == [
        ("Janssens", "ann@vives.be")
    ]
    teachers = client.get("/api/users?role=teacher", headers=headers).json()
    assert "ann@vives.be" in [t["email"] for t in teachers]


def test_import_skips_bad_lines_and_reports_why(client: TestClient):
    headers = ready_to_work(client, "superuser")
    content = (
        "Lisa,Peeters,lisa@student.vives.be\n"
        "Stu,Dent,STUDENT@pmp.local\n"
        "Lisa,Again,lisa@student.vives.be\n"
        ",Nobody,nobody@student.vives.be\n"
        "Bad,Email,not-an-email\n"
        "Too,Few\n"
        "\n"
        "Bram,Claes,bram@student.vives.be\n"
    )

    response = import_csv(client, headers, content)

    assert response.status_code == 200, response.text
    body = response.json()
    assert [u["email"] for u in body["created"]] == [
        "lisa@student.vives.be",
        "bram@student.vives.be",
    ]
    assert [(s["line"], s["reason"]) for s in body["skipped"]] == [
        (2, "The email address student@pmp.local is already in use."),
        (3, "lisa@student.vives.be appears more than once in the file."),
        (4, "A first and a last name are needed."),
        (5, "not-an-email is not a valid email address."),
        (6, "A line needs 3 values: Firstname,Lastname,email."),
    ]


def test_import_of_students_needs_programme_and_year(client: TestClient):
    headers = ready_to_work(client, "superuser")

    response = import_csv(client, headers, "Lisa,Peeters,lisa@x.be\n", year=None)

    assert response.status_code == 422
    assert response.json()["detail"] == "A Student needs a Programme and a Year."


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (b"\xff\xfeL\x00", "The file must be a UTF-8 CSV file."),
        ("a,b,c@d.be\n" * 1001, "The file has more than 1000 lines."),
    ],
)
def test_unreadable_or_huge_files_are_refused(
    client: TestClient, content, message: str
):
    headers = ready_to_work(client, "superuser")

    response = import_csv(client, headers, content)

    assert response.status_code == 422
    assert response.json()["detail"] == message


@pytest.mark.parametrize("role", ["teacher", "student"])
def test_only_the_superuser_imports(client: TestClient, role: str):
    headers = ready_to_work(client, role)

    response = import_csv(client, headers, "Lisa,Peeters,lisa@x.be\n")

    assert response.status_code == 403
