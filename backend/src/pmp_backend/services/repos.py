"""Project repositories on GitHub (spec #49): their names and creating them."""

import re
import unicodedata
from dataclasses import dataclass

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from pmp_backend.domain import ProjectStatus
from pmp_backend.errors import Conflict
from pmp_backend.models import Project, RepoGrant, User
from pmp_backend.services.github import GitHub, GitHubError, RepoInfo
from pmp_backend.services.projects import changeable_project, get_project
from pmp_backend.settings import Settings

REPO_NAME = re.compile(r"^[A-Za-z0-9._-]{1,100}$")


class GitHubConflictError(GitHubError, Conflict):
    pass


@dataclass(frozen=True)
class RepoResult:
    project_id: int
    title: str
    created: bool
    message: str


def is_connected(settings: Settings) -> bool:
    return bool(settings.github_token and settings.github_org)


def check_connected(settings: Settings) -> None:
    if not is_connected(settings):
        raise GitHubConflictError("GitHub isn't connected.")


def suggested_name(title: str) -> str:
    """The title without accents, spaces or punctuation, each word capitalised:
    "Smart Greenhouse" becomes "SmartGreenhouse"."""
    plain = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    words = re.findall(r"[A-Za-z0-9]+", plain)
    return "".join(word[0].upper() + word[1:] for word in words)[:100] or "Project"


def repo_name(project: Project) -> str:
    """The name the repository has, or gets: the chosen one or the suggestion."""
    return project.repo_name or suggested_name(project.title)


def set_repo_name(session: Session, project_id: int, name: str | None) -> Project:
    """Choose the repository name (None: back to the suggestion); only until the
    repository exists."""
    project = changeable_project(session, project_id)
    if project.github_repo_id is not None:
        raise GitHubConflictError(
            f"{project.title} already has its repository, so its name can't change."
        )
    if name is not None and (not REPO_NAME.match(name) or name in {".", ".."}):
        raise GitHubError(
            "A repository name can only use letters, digits, '-', '_' and '.' "
            "(at most 100 characters)."
        )
    project.repo_name = name
    session.commit()
    return project


def create_all(
    session: Session, client: GitHub, settings: Settings
) -> list[RepoResult]:
    """A public, empty repository for every Active Project with Members and no
    repository yet. One failing never stops the others."""
    check_connected(settings)
    candidates = list(
        session.scalars(
            select(Project.id)
            .where(
                Project.status == ProjectStatus.ACTIVE.value,
                Project.github_repo_id.is_(None),
            )
            .order_by(func.lower(Project.title))
        )
    )
    results = []
    for project_id in candidates:
        # Locked, so two Teachers pressing at once don't create it twice.
        project = get_project(session, project_id, lock=True)
        if project.github_repo_id is not None or not project.members:
            session.rollback()
            continue
        try:
            created = client.create_org_repo(settings.github_org, repo_name(project))
        except GitHubError as error:
            session.rollback()
            results.append(RepoResult(project.id, project.title, False, str(error)))
            continue
        project.repo_name = repo_name(project)
        project.github_repo_id = created.id
        project.github_repo_url = created.html_url
        session.commit()
        message = "Created"
        try:
            # Members can start at once (spec #49, story 17).
            check_members(session, client, settings, project.id)
        except GitHubError as error:
            session.rollback()
            message = f"Created, but inviting failed: {error}"
        results.append(RepoResult(project.id, project.title, True, message))
    return results


# Checking members

WRITE, ADMIN = "write", "admin"


@dataclass
class CheckResult:
    invited: list[str]
    removed: list[str]
    updated: list[str]
    repo_gone: bool = False

    @property
    def message(self) -> str:
        if self.repo_gone:
            return "The repository no longer exists on GitHub."
        parts = [
            f"{verb} {', '.join(logins)}."
            for verb, logins in (
                ("Invited", self.invited),
                ("Changed the access of", self.updated),
                ("Removed", self.removed),
            )
            if logins
        ]
        return " ".join(parts) or "Everything was already in order."


def _wanted(project: Project) -> dict[str, tuple[str, str]]:
    """Who should have access, by lower-cased login: active Members write, the
    Product Owner admin, each only with a GitHub username."""
    wanted = {
        member.github_username.lower(): (member.github_username, WRITE)
        for member in project.members
        if member.is_active and member.github_username
    }
    owner = project.product_owner
    if owner.is_active and owner.github_username:
        wanted[owner.github_username.lower()] = (owner.github_username, ADMIN)
    return wanted


def _repository(session: Session, client: GitHub, project: Project) -> RepoInfo:
    if project.github_repo_id is None:
        raise GitHubConflictError(f"{project.title} has no repository yet.")
    info = client.repo(project.github_repo_id)
    if info is None:
        raise RepositoryGoneError()
    if info.html_url != project.github_repo_url:
        # Renamed on GitHub: the id still finds it.
        project.github_repo_url = info.html_url
    return info


class RepositoryGoneError(GitHubConflictError):
    def __init__(self) -> None:
        super().__init__(
            "The repository no longer exists on GitHub. Check members to forget it."
        )


def check_members(
    session: Session, client: GitHub, settings: Settings, project_id: int
) -> CheckResult:
    """Bring the repository's access in line with the Project: invite who is
    missing (again, if the invitation expired), fix permissions, and remove
    platform Users and accounts the platform invited that no longer belong.
    Accounts the platform doesn't know are never touched."""
    check_connected(settings)
    project = get_project(session, project_id, lock=True)
    try:
        info = _repository(session, client, project)
    except RepositoryGoneError:
        project.github_repo_id = None
        project.github_repo_url = None
        session.execute(delete(RepoGrant).where(RepoGrant.project_id == project.id))
        session.commit()
        return CheckResult([], [], [], repo_gone=True)
    full_name = info.full_name
    wanted = _wanted(project)
    granted = set(
        session.scalars(
            select(RepoGrant.login).where(RepoGrant.project_id == project.id)
        )
    )
    usernames = {
        name.lower()
        for name in session.scalars(
            select(User.github_username).where(User.github_username.is_not(None))
        )
    }
    known = usernames | granted
    collaborators = {c.login.lower(): c for c in client.collaborators(full_name)}
    invitations = {i.login.lower(): i for i in client.invitations(full_name)}
    result = CheckResult([], [], [])

    for key, (login, permission) in sorted(wanted.items()):
        collaborator = collaborators.get(key)
        invitation = invitations.get(key)
        if collaborator is not None:
            if collaborator.permission != permission:
                client.invite(full_name, login, permission)
                result.updated.append(login)
        elif (
            invitation is None
            or invitation.expired
            or invitation.permission != permission
        ):
            if invitation is not None:
                client.delete_invitation(full_name, invitation.id)
            client.invite(full_name, login, permission)
            result.invited.append(login)
        if key not in granted:
            session.add(RepoGrant(project_id=project.id, login=key))

    for key in sorted((set(collaborators) | set(invitations)) & known - set(wanted)):
        if key in collaborators:
            client.remove_collaborator(full_name, collaborators[key].login)
            result.removed.append(collaborators[key].login)
        if key in invitations:
            client.delete_invitation(full_name, invitations[key].id)
            if key not in collaborators:
                result.removed.append(invitations[key].login)
        session.execute(
            delete(RepoGrant).where(
                RepoGrant.project_id == project.id, RepoGrant.login == key
            )
        )
    session.commit()
    return result


@dataclass(frozen=True)
class PersonAccess:
    name: str
    role: str
    github_username: str | None
    # "has_access", "invited", "not_invited" or "no_username".
    status: str


def people_access(
    session: Session, client: GitHub, settings: Settings, project_id: int
) -> tuple[str, list[PersonAccess]]:
    """The repository URL and, for the Product Owner and each Member, their
    access, read live from GitHub."""
    check_connected(settings)
    project = get_project(session, project_id)
    info = _repository(session, client, project)
    collaborators = {c.login.lower() for c in client.collaborators(info.full_name)}
    pending = {
        i.login.lower() for i in client.invitations(info.full_name) if not i.expired
    }

    def access(user: User, role: str) -> PersonAccess:
        login = user.github_username
        if not login:
            status = "no_username"
        elif login.lower() in collaborators:
            status = "has_access"
        elif login.lower() in pending:
            status = "invited"
        else:
            status = "not_invited"
        return PersonAccess(user.full_name, role, login, status)

    people = [access(project.product_owner, "Product Owner")]
    people += [access(member, "Member") for member in project.members]
    return info.html_url, people


def check_all(
    session: Session, client: GitHub, settings: Settings
) -> list[tuple[Project, str]]:
    """Check the members of every Active Project's repository."""
    check_connected(settings)
    ids = list(
        session.scalars(
            select(Project.id)
            .where(
                Project.status == ProjectStatus.ACTIVE.value,
                Project.github_repo_id.is_not(None),
            )
            .order_by(func.lower(Project.title))
        )
    )
    results = []
    for project_id in ids:
        try:
            message = check_members(session, client, settings, project_id).message
        except GitHubError as error:
            session.rollback()
            message = f"Failed. {error}"
        results.append((get_project(session, project_id), message))
    return results
