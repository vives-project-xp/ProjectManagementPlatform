"""The only place that talks to GitHub (spec #49). The app keeps one client in
`app.state.github`; tests put `testing.FakeGitHub` there instead."""

import re
from dataclasses import dataclass
from typing import Protocol

import httpx

from pmp_backend.errors import NotFound, Refused, Unavailable
from pmp_backend.settings import Settings

# GitHub's own rule: letters, digits and single hyphens, not at either end.
USERNAME = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}$")


class GitHubError(Refused):
    """A GitHub action was refused; the message is fit to show."""


class GitHubAccountNotFoundError(GitHubError, NotFound):
    pass


class GitHubUnavailableError(GitHubError, Unavailable):
    def __init__(self) -> None:
        super().__init__("GitHub can't be reached. Try again later.")


@dataclass(frozen=True)
class GitHubAccount:
    login: str
    name: str | None
    avatar_url: str


@dataclass(frozen=True)
class CreatedRepo:
    id: int
    html_url: str


def repo_exists_error(org: str, name: str) -> GitHubError:
    return GitHubError(
        f"A repository called {name} already exists in {org}. "
        "Choose another Repository name."
    )


class GitHub(Protocol):
    def user(self, username: str) -> GitHubAccount | None:
        """The account with this username (any capitalisation), or None."""
        ...

    def create_org_repo(self, org: str, name: str) -> CreatedRepo:
        """A new public, completely empty repository in the organisation."""
        ...


class HttpGitHub:
    """GitHub's REST API. Without a token, lookups still work (at GitHub's lower
    anonymous rate limit)."""

    def __init__(self, settings: Settings) -> None:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if settings.github_token:
            headers["Authorization"] = f"Bearer {settings.github_token}"
        self._client = httpx.Client(
            base_url=settings.github_api_url, headers=headers, timeout=10
        )

    def _get(self, path: str) -> httpx.Response:
        try:
            return self._client.get(path)
        except httpx.HTTPError as error:
            raise GitHubUnavailableError() from error

    def _send(self, method: str, path: str, **kwargs) -> httpx.Response:
        try:
            return self._client.request(method, path, **kwargs)
        except httpx.HTTPError as error:
            raise GitHubUnavailableError() from error

    def _refused(self, response: httpx.Response, org: str) -> GitHubError:
        if response.status_code == 401:
            return GitHubError("GitHub refused the token. Check GITHUB_TOKEN.")
        if response.status_code in (403, 404):
            return GitHubError(
                f"The GitHub token may not do this in {org}. Check its permissions."
            )
        return GitHubUnavailableError()

    def create_org_repo(self, org: str, name: str) -> CreatedRepo:
        response = self._send(
            "POST",
            f"/orgs/{org}/repos",
            json={"name": name, "private": False, "auto_init": False},
        )
        if response.status_code == 422:
            # GitHub's way of saying the name is taken.
            raise repo_exists_error(org, name)
        if response.is_error:
            raise self._refused(response, org)
        body = response.json()
        return CreatedRepo(id=body["id"], html_url=body["html_url"])

    def user(self, username: str) -> GitHubAccount | None:
        response = self._get(f"/users/{username}")
        if response.status_code == 404:
            return None
        if response.is_error:
            raise GitHubUnavailableError()
        body = response.json()
        return GitHubAccount(
            login=body["login"], name=body.get("name"), avatar_url=body["avatar_url"]
        )


def find_account(github: GitHub, username: str) -> GitHubAccount:
    """The GitHub account called `username`; refused when invalid or unknown."""
    username = username.strip()
    if not USERNAME.match(username):
        raise GitHubError("That isn't a valid GitHub username.")
    account = github.user(username)
    if account is None:
        raise GitHubAccountNotFoundError(f"No GitHub account is called {username}.")
    return account
