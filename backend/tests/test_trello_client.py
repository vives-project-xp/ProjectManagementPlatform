"""The real Trello client against a fake Trello API (httpx.MockTransport)."""

import httpx
import pytest

from pmp_backend.services.trello import HttpTrello, TrelloError
from pmp_backend.settings import Settings


def client_with(settings: Settings, handler) -> HttpTrello:
    trello = HttpTrello(settings)
    trello._client = httpx.Client(
        base_url="https://trello.test/1", transport=httpx.MockTransport(handler)
    )
    return trello


def test_someone_without_trello_is_invited_as_normal_instead_of_admin(
    settings: Settings,
):
    """Seen on 2026-11-12: Trello answers 403 "Bad member type" when an email
    without a Trello account is invited (or promoted) as admin."""
    members = [{"idMember": "owner", "memberType": "admin"}]
    asked = []

    def trello(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json=members)
        asked.append(request.url.params["type"])
        if request.url.params["type"] == "admin":
            return httpx.Response(403, text="Bad member type")
        members.append({"idMember": "new", "memberType": "normal", "unconfirmed": True})
        return httpx.Response(200, json={"memberships": members})

    member = client_with(settings, trello).invite("b1", "po@vives.be", "admin")

    assert member == "new"
    assert asked == ["admin", "normal"]


def test_other_refusals_still_fail(settings: Settings):
    def trello(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json=[])
        return httpx.Response(403, text="Bad member type")

    with pytest.raises(TrelloError, match="Bad member type"):
        client_with(settings, trello).invite("b1", "lisa@vives.be", "normal")
