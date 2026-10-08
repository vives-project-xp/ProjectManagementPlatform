"""Project repositories on GitHub (spec #49): their names and creating them."""

import re
import unicodedata
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from pmp_backend.domain import ProjectStatus
from pmp_backend.errors import Conflict
from pmp_backend.models import Project
from pmp_backend.services.github import GitHub, GitHubError
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
        results.append(RepoResult(project.id, project.title, True, "Created"))
    return results
