"""The only place that talks to Trello (spec #61). The app keeps one client in
`app.state.trello`; tests put `testing.FakeTrello` there instead."""

from dataclasses import dataclass
from typing import Protocol

import httpx

from pmp_backend.errors import Refused, Unavailable
from pmp_backend.settings import Settings

# Every new board gets these lists, in this order, and nothing else.
LISTS = ("Backlog", "To do", "Doing", "Review", "Done")

NORMAL, ADMIN = "normal", "admin"


class TrelloError(Refused):
    """A Trello action was refused; the message is fit to show."""


class TrelloUnavailableError(TrelloError, Unavailable):
    def __init__(self) -> None:
        super().__init__("Trello can't be reached. Try again later.")


@dataclass(frozen=True)
class CreatedBoard:
    id: str
    url: str


@dataclass(frozen=True)
class BoardInfo:
    name: str
    url: str


@dataclass(frozen=True)
class Membership:
    member_id: str
    # "normal", "admin" or "observer".
    member_type: str
    # Invited by email, but no Trello account with that email yet.
    unconfirmed: bool


class Trello(Protocol):
    def create_workspace(self, name: str) -> str:
        """A new free Workspace with this display name; its id."""
        ...

    def delete_workspace(self, workspace_id: str) -> None: ...

    def create_board(self, workspace_id: str, name: str) -> CreatedBoard:
        """A new private board in the Workspace, without any lists."""
        ...

    def add_list(self, board_id: str, name: str) -> None:
        """A list at the right end of the board."""
        ...

    def board(self, board_id: str) -> BoardInfo | None:
        """The board, or None when it was deleted."""
        ...

    def rename(self, workspace_id: str, board_id: str, name: str) -> None:
        """Give the Workspace and its board this name."""
        ...

    def memberships(self, board_id: str) -> list[Membership]: ...

    def invite(self, board_id: str, email: str, member_type: str) -> str | None:
        """Add the person with this email to the board ("normal" or "admin"): at
        once with a Trello account, unconfirmed without one. The Trello member id,
        or None when the email already was on the board."""
        ...

    def set_member_type(
        self, board_id: str, member_id: str, member_type: str
    ) -> None: ...

    def remove_member(self, board_id: str, member_id: str) -> None: ...


class HttpTrello:
    """Trello's REST API, as the dedicated account of TRELLO_API_KEY/TOKEN."""

    def __init__(self, settings: Settings) -> None:
        headers = {}
        if settings.trello_api_key and settings.trello_token:
            # In a header rather than the query string, so URLs in logs and
            # error messages never carry the token.
            headers["Authorization"] = (
                f'OAuth oauth_consumer_key="{settings.trello_api_key}", '
                f'oauth_token="{settings.trello_token}"'
            )
        self._client = httpx.Client(
            base_url=settings.trello_api_url, headers=headers, timeout=10
        )

    def _send(self, method: str, path: str, **params: str) -> httpx.Response:
        try:
            response = self._client.request(method, path, params=params)
        except httpx.HTTPError as error:
            raise TrelloUnavailableError() from error
        if response.status_code == 401:
            raise TrelloError(
                "Trello refused the API key or token. "
                "Check TRELLO_API_KEY and TRELLO_TOKEN."
            )
        if response.status_code == 429 or response.status_code >= 500:
            raise TrelloUnavailableError()
        if response.is_error:
            error = TrelloError(f"Trello refused: {_reason(response)}")
            # A deleted board or Workspace.
            if response.status_code == 404:
                error.code = "not_found"
            raise error
        return response

    def create_workspace(self, name: str) -> str:
        return self._send("POST", "/organizations", displayName=name).json()["id"]

    def delete_workspace(self, workspace_id: str) -> None:
        self._send("DELETE", f"/organizations/{workspace_id}")

    def create_board(self, workspace_id: str, name: str) -> CreatedBoard:
        body = self._send(
            "POST",
            "/boards",
            name=name,
            idOrganization=workspace_id,
            defaultLists="false",
            defaultLabels="false",
            prefs_permissionLevel="private",
        ).json()
        return CreatedBoard(id=body["id"], url=body["url"])

    def add_list(self, board_id: str, name: str) -> None:
        self._send("POST", f"/boards/{board_id}/lists", name=name, pos="bottom")

    def board(self, board_id: str) -> BoardInfo | None:
        try:
            body = self._send("GET", f"/boards/{board_id}", fields="name,url").json()
        except TrelloError as error:
            if error.code == "not_found":
                return None
            raise
        return BoardInfo(name=body["name"], url=body["url"])

    def rename(self, workspace_id: str, board_id: str, name: str) -> None:
        self._send("PUT", f"/organizations/{workspace_id}", displayName=name)
        self._send("PUT", f"/boards/{board_id}", name=name)

    def set_member_type(self, board_id: str, member_id: str, member_type: str) -> None:
        self._send("PUT", f"/boards/{board_id}/members/{member_id}", type=member_type)

    def remove_member(self, board_id: str, member_id: str) -> None:
        self._send("DELETE", f"/boards/{board_id}/members/{member_id}")

    def memberships(self, board_id: str) -> list[Membership]:
        response = self._send("GET", f"/boards/{board_id}/memberships")
        return [_membership(item) for item in response.json()]

    def invite(self, board_id: str, email: str, member_type: str) -> str | None:
        before = {m.member_id for m in self.memberships(board_id)}
        try:
            body = self._send(
                "PUT", f"/boards/{board_id}/members", email=email, type=member_type
            ).json()
        except TrelloError as error:
            # Trello refuses an email that is already on the board ("Member
            # already invited", seen in the real try of #62).
            if "already" in str(error).lower():
                return None
            raise
        # Trello doesn't say which member the email became: the new one.
        added = {item["idMember"] for item in body["memberships"]} - before
        return added.pop() if len(added) == 1 else None


def _membership(item: dict) -> Membership:
    return Membership(
        member_id=item["idMember"],
        member_type=item["memberType"],
        unconfirmed=bool(item.get("unconfirmed")),
    )


def _reason(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text.strip()[:200] or f"error {response.status_code}"
    if isinstance(body, dict) and body.get("message"):
        return str(body["message"])[:200]
    return f"error {response.status_code}"
