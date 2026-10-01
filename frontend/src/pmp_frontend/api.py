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

    def __init__(self, status_code: int, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        # Set when the page must react specifically, e.g. "move_confirmation_needed".
        self.code = code

    @property
    def is_unauthorized(self) -> bool:
        return self.status_code == 401


def _validation_message(errors: list[Any]) -> str:
    """Turn the backend's field validation errors into one readable sentence."""
    problems = []
    for error in errors:
        location = error.get("loc") or ["value"]
        field = str(location[-1]).replace("_", " ").capitalize()
        if error.get("type") == "string_pattern_mismatch":
            problems.append(f"{field} is not valid.")
        else:
            problems.append(f"{field}: {error.get('msg', 'is not valid')}.")
    return " ".join(problems) or "Something went wrong."


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
            body = response.json()
        except ValueError:
            body = {}
        detail = body.get("detail")
        if isinstance(detail, str):
            message = detail
        elif isinstance(detail, list):
            message = _validation_message(detail)
        else:
            message = "Something went wrong."
        raise ApiError(response.status_code, message, body.get("code"))
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


async def list_users(
    token: str, *, role: str | None = None, active: bool | None = None
) -> list[dict[str, Any]]:
    filters = []
    if role:
        filters.append(f"role={role}")
    if active is not None:
        filters.append(f"active={str(active).lower()}")
    query = f"?{'&'.join(filters)}" if filters else ""
    return await _request("GET", f"/api/users{query}", token=token)


async def get_user(token: str, user_id: int) -> dict[str, Any]:
    return await _request("GET", f"/api/users/{user_id}", token=token)


async def update_user(
    token: str, user_id: int, fields: dict[str, Any]
) -> dict[str, Any]:
    """`fields`: first_name, last_name, email, programme, year (never the Role)."""
    return await _request("PUT", f"/api/users/{user_id}", token=token, json=fields)


async def deactivate_user(token: str, user_id: int) -> dict[str, Any]:
    return await _request("POST", f"/api/users/{user_id}/deactivate", token=token)


async def reactivate_user(token: str, user_id: int) -> dict[str, Any]:
    return await _request("POST", f"/api/users/{user_id}/reactivate", token=token)


async def reset_password(token: str, user_id: int, temporary_password: str) -> None:
    await _request(
        "POST",
        f"/api/users/{user_id}/reset-password",
        token=token,
        json={"temporary_password": temporary_password},
    )


async def create_user(token: str, new_user: dict[str, Any]) -> dict[str, Any]:
    """Create a Teacher or Student; `new_user` matches the backend's create body."""
    return await _request("POST", "/api/users", token=token, json=new_user)


async def teachers(token: str) -> list[dict[str, Any]]:
    """The active Teachers (id and name), to choose a Product Owner from."""
    return await _request("GET", "/api/teachers", token=token)


MOVE_CONFIRMATION_NEEDED = "move_confirmation_needed"


async def students(token: str) -> list[dict[str, Any]]:
    """Every Student with their Project (or None), to choose Members from."""
    return await _request("GET", "/api/students", token=token)


async def add_member(
    token: str, project_id: int, student_id: int, *, confirm_move: bool = False
) -> dict[str, Any]:
    """The Project's details after adding; raises ApiError with code
    MOVE_CONFIRMATION_NEEDED when the Student is a Member elsewhere."""
    return await _request(
        "POST",
        f"/api/projects/{project_id}/members",
        token=token,
        json={"student_id": student_id, "confirm_move": confirm_move},
    )


async def remove_member(token: str, project_id: int, student_id: int) -> dict[str, Any]:
    return await _request(
        "DELETE", f"/api/projects/{project_id}/members/{student_id}", token=token
    )


async def list_projects(token: str) -> list[dict[str, Any]]:
    return await _request("GET", "/api/projects", token=token)


async def get_project(token: str, project_id: int) -> dict[str, Any]:
    return await _request("GET", f"/api/projects/{project_id}", token=token)


async def create_project(token: str, fields: dict[str, Any]) -> dict[str, Any]:
    """`fields`: title, description, product_owner_id, team_size_min/max."""
    return await _request("POST", "/api/projects", token=token, json=fields)


async def update_project(
    token: str, project_id: int, fields: dict[str, Any]
) -> dict[str, Any]:
    return await _request(
        "PUT", f"/api/projects/{project_id}", token=token, json=fields
    )
