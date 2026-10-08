"""The only way the frontend talks to the backend: its REST API over HTTP (ADR 0003)."""

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

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


async def _response(
    method: str,
    path: str,
    *,
    token: str | None = None,
    json: Any = None,
    files: Any = None,
) -> httpx.Response:
    """The backend's answer; ApiError when it refuses or cannot be reached."""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        async with _client() as client:
            response = await client.request(
                method, path, headers=headers, json=json, files=files
            )
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
    return response


async def _request(
    method: str,
    path: str,
    *,
    token: str | None = None,
    json: Any = None,
    files: Any = None,
) -> Any:
    response = await _response(method, path, token=token, json=json, files=files)
    return response.json() if response.content else None


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


async def dev_login_users() -> list[dict[str, Any]] | None:
    """The Users the test login offers (id, name, role), or None when it is off
    (or the backend cannot be reached)."""
    try:
        return await _request("GET", "/api/dev-login/users")
    except ApiError:
        return None


async def dev_login(user_id: int) -> tuple[str, CurrentUser]:
    """Log in as this User without a password (test login only)."""
    body = await _request("POST", "/api/dev-login", json={"user_id": user_id})
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


async def list_programmes(token: str) -> list[dict[str, Any]]:
    """The Programme list (id and name), sorted by name."""
    return await _request("GET", "/api/programmes", token=token)


async def programmes(token: str) -> list[str]:
    """The Programme names, to pick from in forms and filters."""
    return [programme["name"] for programme in await list_programmes(token)]


async def add_programme(token: str, name: str) -> dict[str, Any]:
    return await _request("POST", "/api/programmes", token=token, json={"name": name})


async def rename_programme(token: str, programme_id: int, name: str) -> dict[str, Any]:
    """Also renames the Programme for every User who has it."""
    return await _request(
        "PUT", f"/api/programmes/{programme_id}", token=token, json={"name": name}
    )


async def remove_programme(token: str, programme_id: int) -> None:
    await _request("DELETE", f"/api/programmes/{programme_id}", token=token)


async def list_users(
    token: str, *, role: str | None = None, active: bool | None = None
) -> list[dict[str, Any]]:
    params: dict[str, str] = {}
    if role:
        params["role"] = role
    if active is not None:
        params["active"] = str(active).lower()
    query = f"?{urlencode(params)}" if params else ""
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


async def delete_user(token: str, user_id: int) -> None:
    await _request("DELETE", f"/api/users/{user_id}", token=token)


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


async def students(
    token: str,
    *,
    without_project: bool = False,
    programme: str | None = None,
    year: str | None = None,
) -> list[dict[str, Any]]:
    """Students with their Project (or None), optionally filtered."""
    params: dict[str, str] = {}
    if without_project:
        params["without_project"] = "true"
    if programme:
        params["programme"] = programme
    if year:
        params["year"] = year
    query = f"?{urlencode(params)}" if params else ""
    return await _request("GET", f"/api/students{query}", token=token)


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


async def my_project(token: str) -> dict[str, Any] | None:
    """The logged-in Student's Project (title, description, product_owner,
    fellow_members), or None when they have none yet."""
    return await _request("GET", "/api/my-project", token=token)


async def list_projects(
    token: str, *, status: str | None = None
) -> list[dict[str, Any]]:
    """All Projects, or only those with `status` ("active" or "archived")."""
    query = f"?status={status}" if status else ""
    return await _request("GET", f"/api/projects{query}", token=token)


async def set_open_for_choice(
    token: str, project_id: int, value: bool
) -> dict[str, Any]:
    return await _request(
        "PUT",
        f"/api/projects/{project_id}/open-for-choice",
        token=token,
        json={"open": value},
    )


async def top3_round(token: str) -> dict[str, Any]:
    """The Top 3 round: `deadline` (ISO, or None before the first) and `is_open`."""
    return await _request("GET", "/api/top3/round", token=token)


async def set_top3_deadline(token: str, deadline: str) -> dict[str, Any]:
    """Open, reopen or move the round; `deadline` is ISO with a time zone."""
    return await _request(
        "PUT", "/api/top3/round", token=token, json={"deadline": deadline}
    )


async def close_top3_round(token: str) -> dict[str, Any]:
    return await _request("POST", "/api/top3/round/close", token=token)


async def start_new_top3_round(token: str, deadline: str) -> dict[str, Any]:
    """Clear every Top 3 and open the round with this deadline."""
    return await _request(
        "POST", "/api/top3/round/new", token=token, json={"deadline": deadline}
    )


async def my_top3(token: str) -> dict[str, Any]:
    """The logged-in Student's view of the Top 3: round, can_submit, places,
    projects to choose from, and their submitted top3 (or None)."""
    return await _request("GET", "/api/my-top3", token=token)


async def submit_top3(token: str, project_ids: list[int]) -> dict[str, Any]:
    """Submit a ranked Top 3: the first id is the 1st choice."""
    return await _request(
        "POST", "/api/my-top3", token=token, json={"project_ids": project_ids}
    )


async def top3_overview(
    token: str,
    *,
    programme: str | None = None,
    year: str | None = None,
    without_top3: bool = False,
) -> dict[str, Any]:
    """Every active Student with their Top 3 (`students`), and per open Project
    how often it was chosen 1st, 2nd and 3rd (`summary`)."""
    params: dict[str, str] = {}
    if programme:
        params["programme"] = programme
    if year:
        params["year"] = year
    if without_top3:
        params["without_top3"] = "true"
    query = f"?{urlencode(params)}" if params else ""
    return await _request("GET", f"/api/top3/overview{query}", token=token)


async def reset_top3(token: str, student_id: int) -> None:
    await _request("DELETE", f"/api/top3/students/{student_id}", token=token)


async def delete_project(token: str, project_id: int) -> None:
    await _request("DELETE", f"/api/projects/{project_id}", token=token)


async def archive_project(token: str, project_id: int) -> dict[str, Any]:
    return await _request("POST", f"/api/projects/{project_id}/archive", token=token)


async def restore_project(token: str, project_id: int) -> dict[str, Any]:
    return await _request("POST", f"/api/projects/{project_id}/restore", token=token)


async def get_project(token: str, project_id: int) -> dict[str, Any]:
    return await _request("GET", f"/api/projects/{project_id}", token=token)


async def upload_photo(
    token: str, project_id: int, name: str, data: bytes, content_type: str
) -> dict[str, Any]:
    return await _request(
        "PUT",
        f"/api/projects/{project_id}/photo",
        token=token,
        files={"photo": (name, data, content_type)},
    )


async def remove_photo(token: str, project_id: int) -> dict[str, Any]:
    return await _request("DELETE", f"/api/projects/{project_id}/photo", token=token)


async def project_photo(token: str, project_id: int) -> tuple[bytes, str]:
    """The photo's bytes and media type."""
    response = await _response("GET", f"/api/projects/{project_id}/photo", token=token)
    return response.content, response.headers["content-type"]


async def create_project(token: str, fields: dict[str, Any]) -> dict[str, Any]:
    """`fields`: title, description, product_owner_id, team_size_min/max."""
    return await _request("POST", "/api/projects", token=token, json=fields)


async def update_project(
    token: str, project_id: int, fields: dict[str, Any]
) -> dict[str, Any]:
    return await _request(
        "PUT", f"/api/projects/{project_id}", token=token, json=fields
    )
