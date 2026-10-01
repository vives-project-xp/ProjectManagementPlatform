"""The only way the frontend talks to the backend: its REST API over HTTP (ADR 0003)."""

from dataclasses import dataclass
from typing import Any

import httpx

from pmp_frontend.settings import Settings

_transport: httpx.AsyncBaseTransport | None = None


def use_transport(transport: httpx.AsyncBaseTransport | None) -> None:
    """Send API calls through `transport` instead of the network (used by tests)."""
    global _transport
    _transport = transport


def _client() -> httpx.AsyncClient:
    base_url = "http://backend" if _transport else Settings().backend_url
    return httpx.AsyncClient(base_url=base_url, transport=_transport, timeout=5)


class ApiError(Exception):
    """The backend refused a request; `message` is fit to show to the User."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message

    @property
    def is_unauthorized(self) -> bool:
        return self.status_code == 401


async def _request(
    method: str, path: str, *, token: str | None = None, json: Any = None
) -> Any:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        async with _client() as client:
            response = await client.request(method, path, headers=headers, json=json)
    except httpx.HTTPError as error:
        raise ApiError(503, "The server cannot be reached. Try again later.") from error
    if response.is_error:
        try:
            detail = response.json().get("detail")
        except ValueError:
            detail = None
        message = detail if isinstance(detail, str) else "Something went wrong."
        raise ApiError(response.status_code, message)
    return response.json() if response.content else None


@dataclass(frozen=True)
class Health:
    backend_online: bool
    database_online: bool


async def get_health() -> Health:
    try:
        async with _client() as client:
            response = await client.get("/api/health")
        body = response.json()
    except (httpx.HTTPError, ValueError):
        # Unreachable, or something answered that is not our backend's JSON.
        return Health(backend_online=False, database_online=False)
    return Health(backend_online=True, database_online=body.get("database") == "ok")


@dataclass(frozen=True)
class CurrentUser:
    first_name: str
    last_name: str
    email: str
    role: str
    must_change_password: bool

    @classmethod
    def of(cls, body: dict[str, Any]) -> "CurrentUser":
        return cls(
            first_name=body["first_name"],
            last_name=body["last_name"],
            email=body["email"],
            role=body["role"],
            must_change_password=body["must_change_password"],
        )

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"


async def login(email: str, password: str) -> tuple[str, CurrentUser]:
    """The token and the logged-in User."""
    body = await _request(
        "POST", "/api/auth/login", json={"email": email, "password": password}
    )
    return body["access_token"], CurrentUser.of(body["user"])


async def me(token: str) -> CurrentUser:
    return CurrentUser.of(await _request("GET", "/api/auth/me", token=token))


async def change_password(token: str, current_password: str, new_password: str) -> None:
    await _request(
        "POST",
        "/api/auth/change-password",
        token=token,
        json={"current_password": current_password, "new_password": new_password},
    )


async def logout(token: str) -> None:
    await _request("POST", "/api/auth/logout", token=token)


async def programmes(token: str) -> list[str]:
    return await _request("GET", "/api/programmes", token=token)


async def list_users(token: str) -> list[dict[str, Any]]:
    return await _request("GET", "/api/users", token=token)


async def create_user(token: str, new_user: dict[str, Any]) -> dict[str, Any]:
    """Create a Teacher or Student; `new_user` matches the backend's create body."""
    return await _request("POST", "/api/users", token=token, json=new_user)
