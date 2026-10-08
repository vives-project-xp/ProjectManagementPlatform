from typing import Annotated

from fastapi import APIRouter
from pydantic import BaseModel, StringConstraints

from pmp_backend.api.deps import (
    CurrentUserDep,
    GitHubDep,
    SessionDep,
    SettingsDep,
    TeacherOrSuperuserDep,
)
from pmp_backend.api.schemas import UserOut
from pmp_backend.services import github, repos, users

router = APIRouter(prefix="/api", tags=["github"])


class GitHubAccountOut(BaseModel):
    login: str
    name: str | None
    avatar_url: str


class GitHubUsernameIn(BaseModel):
    # None (or empty) clears it.
    github_username: (
        Annotated[str, StringConstraints(strip_whitespace=True, max_length=39)] | None
    )


@router.get("/github/users/{username}")
def find_account(
    username: str, client: GitHubDep, user: CurrentUserDep
) -> GitHubAccountOut:
    account = github.find_account(client, username)
    return GitHubAccountOut(
        login=account.login, name=account.name, avatar_url=account.avatar_url
    )


@router.put("/me/github-username")
def set_own_github_username(
    body: GitHubUsernameIn, session: SessionDep, client: GitHubDep, user: CurrentUserDep
) -> UserOut:
    saved = users.set_github_username(session, client, user.id, body.github_username)
    return UserOut.model_validate(saved)


class GitHubStatusOut(BaseModel):
    connected: bool
    org: str | None


class RepoResultOut(BaseModel):
    project_id: int
    title: str
    created: bool
    message: str


@router.get("/github/status")
def github_status(
    settings: SettingsDep, user: TeacherOrSuperuserDep
) -> GitHubStatusOut:
    return GitHubStatusOut(
        connected=repos.is_connected(settings), org=settings.github_org or None
    )


@router.post("/github/repos")
def create_repos(
    session: SessionDep,
    client: GitHubDep,
    settings: SettingsDep,
    user: TeacherOrSuperuserDep,
) -> list[RepoResultOut]:
    """Create repositories for all Projects that need one; a result per Project."""
    return [
        RepoResultOut(**vars(result))
        for result in repos.create_all(session, client, settings)
    ]


class CheckOut(BaseModel):
    invited: list[str]
    removed: list[str]
    updated: list[str]
    repo_gone: bool
    message: str


class CheckAllOut(BaseModel):
    project_id: int
    title: str
    message: str


class PersonAccessOut(BaseModel):
    name: str
    role: str
    github_username: str | None
    status: str


class RepositoryAccessOut(BaseModel):
    repo_url: str
    people: list[PersonAccessOut]


@router.post("/projects/{project_id}/github/check")
def check_members(
    project_id: int,
    session: SessionDep,
    client: GitHubDep,
    settings: SettingsDep,
    user: TeacherOrSuperuserDep,
) -> CheckOut:
    result = repos.check_members(session, client, settings, project_id)
    return CheckOut(**vars(result), message=result.message)


@router.post("/github/check-all")
def check_all_members(
    session: SessionDep,
    client: GitHubDep,
    settings: SettingsDep,
    user: TeacherOrSuperuserDep,
) -> list[CheckAllOut]:
    return [
        CheckAllOut(project_id=project.id, title=project.title, message=message)
        for project, message in repos.check_all(session, client, settings)
    ]


@router.get("/projects/{project_id}/github")
def repository_access(
    project_id: int,
    session: SessionDep,
    client: GitHubDep,
    settings: SettingsDep,
    user: TeacherOrSuperuserDep,
) -> RepositoryAccessOut:
    url, people = repos.people_access(session, client, settings, project_id)
    return RepositoryAccessOut(
        repo_url=url, people=[PersonAccessOut(**vars(person)) for person in people]
    )
