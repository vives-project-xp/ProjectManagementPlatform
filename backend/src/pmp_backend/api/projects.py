from typing import Annotated

from fastapi import APIRouter, Response, UploadFile, status
from pydantic import BaseModel, Field, StringConstraints

from pmp_backend.api.deps import (
    CurrentUserDep,
    SessionDep,
    SettingsDep,
    StudentDep,
    TeacherOrSuperuserDep,
)
from pmp_backend.api.schemas import PersonOut, StudentOut
from pmp_backend.domain import ProjectStatus
from pmp_backend.models import Project, User
from pmp_backend.services import memberships, photos, projects, repos, top3
from pmp_backend.services.projects import ProjectFields

router = APIRouter(prefix="/api", tags=["projects"])


class ProjectOut(BaseModel):
    id: int
    title: str
    description: str | None
    product_owner: PersonOut
    team_size_min: int
    team_size_max: int
    member_count: int
    status: str
    # Null without a photo; changes with every upload.
    photo_version: int | None
    open_for_choice: bool
    # The repository's name (chosen or suggested) and its URL once it exists.
    repo_name: str
    repo_url: str | None

    @classmethod
    def of(cls, project: Project) -> "ProjectOut":
        return cls(
            id=project.id,
            title=project.title,
            description=project.description,
            product_owner=PersonOut.of(project.product_owner),
            team_size_min=project.team_size_min,
            team_size_max=project.team_size_max,
            member_count=project.member_count,
            status=project.status,
            photo_version=project.photo_version,
            open_for_choice=project.open_for_choice,
            repo_name=repos.repo_name(project),
            repo_url=project.github_repo_url,
        )


class MakerOut(BaseModel):
    """A Member at archive time, kept on the Project forever ("Made by")."""

    name: str
    programme: str | None
    year: str | None


class Top3RankOut(BaseModel):
    """The rank (1–3) a Student gave this Project in their Top 3."""

    student_id: int
    rank: int


class ProjectDetailsOut(ProjectOut):
    members: list[StudentOut]
    makers: list[MakerOut]
    top3_ranks: list[Top3RankOut]

    @classmethod
    def of(cls, project: Project) -> "ProjectDetailsOut":
        return cls(
            **ProjectOut.of(project).model_dump(),
            members=[StudentOut.of(member) for member in project.members],
            makers=[MakerOut.model_validate(maker) for maker in project.makers],
            top3_ranks=[
                Top3RankOut(student_id=choice.student_id, rank=choice.rank)
                for choice in sorted(
                    project.top3_choices, key=lambda c: (c.rank, c.student_id)
                )
            ],
        )


class MyProjectOut(BaseModel):
    """A Student's own Project: only what a Student may see of it."""

    id: int
    title: str
    description: str | None
    product_owner: str
    fellow_members: list[str]
    photo_version: int | None

    @classmethod
    def of(cls, project: Project, student: User) -> "MyProjectOut":
        return cls(
            id=project.id,
            title=project.title,
            description=project.description,
            product_owner=project.product_owner.full_name,
            fellow_members=[
                member.full_name
                for member in project.members
                if member.id != student.id
            ],
            photo_version=project.photo_version,
        )


class ProjectIn(BaseModel):
    title: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
    ]
    description: Annotated[str, StringConstraints(strip_whitespace=True)] | None = None
    product_owner_id: int
    team_size_min: int = Field(ge=1)
    team_size_max: int = Field(ge=1)

    def fields(self) -> ProjectFields:
        return ProjectFields(**self.model_dump())


class OpenForChoiceIn(BaseModel):
    open: bool


class RepoNameIn(BaseModel):
    # None: back to the name suggested from the title.
    repo_name: Annotated[str, StringConstraints(strip_whitespace=True)] | None


class MemberIn(BaseModel):
    student_id: int
    # Must be true to move a Student who is a Member of another Project.
    confirm_move: bool = False


@router.get("/teachers")
def teachers(session: SessionDep, user: TeacherOrSuperuserDep) -> list[PersonOut]:
    """The active Teachers, to choose a Product Owner from."""
    return [PersonOut.of(teacher) for teacher in projects.active_teachers(session)]


@router.get("/my-project")
def my_project(user: StudentDep) -> MyProjectOut | None:
    """The logged-in Student's Project, or None when they have none yet."""
    return MyProjectOut.of(user.project, user) if user.project else None


@router.get("/projects")
def list_projects(
    session: SessionDep,
    user: TeacherOrSuperuserDep,
    status: ProjectStatus | None = None,
) -> list[ProjectOut]:
    found = projects.list_projects(session, status=status)
    return [ProjectOut.of(project) for project in found]


@router.post("/projects/{project_id}/archive")
def archive_project(
    project_id: int, session: SessionDep, user: TeacherOrSuperuserDep
) -> ProjectDetailsOut:
    return ProjectDetailsOut.of(projects.archive_project(session, project_id))


@router.post("/projects/{project_id}/restore")
def restore_project(
    project_id: int, session: SessionDep, user: TeacherOrSuperuserDep
) -> ProjectDetailsOut:
    return ProjectDetailsOut.of(projects.restore_project(session, project_id))


@router.post("/projects", status_code=status.HTTP_201_CREATED)
def create_project(
    body: ProjectIn, session: SessionDep, user: TeacherOrSuperuserDep
) -> ProjectDetailsOut:
    return ProjectDetailsOut.of(projects.create_project(session, body.fields()))


@router.get("/projects/{project_id}")
def get_project(
    project_id: int, session: SessionDep, user: TeacherOrSuperuserDep
) -> ProjectDetailsOut:
    return ProjectDetailsOut.of(projects.get_project(session, project_id))


@router.put("/projects/{project_id}")
def update_project(
    project_id: int, body: ProjectIn, session: SessionDep, user: TeacherOrSuperuserDep
) -> ProjectDetailsOut:
    project = projects.update_project(session, project_id, body.fields())
    return ProjectDetailsOut.of(project)


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: int,
    session: SessionDep,
    settings: SettingsDep,
    user: TeacherOrSuperuserDep,
) -> Response:
    photos.delete_project(session, settings.photos_dir, project_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/projects/{project_id}/open-for-choice")
def set_open_for_choice(
    project_id: int,
    body: OpenForChoiceIn,
    session: SessionDep,
    user: TeacherOrSuperuserDep,
) -> ProjectDetailsOut:
    project = top3.set_open_for_choice(session, project_id, body.open)
    return ProjectDetailsOut.of(project)


@router.put("/projects/{project_id}/repo-name")
def set_repo_name(
    project_id: int, body: RepoNameIn, session: SessionDep, user: TeacherOrSuperuserDep
) -> ProjectDetailsOut:
    project = repos.set_repo_name(session, project_id, body.repo_name or None)
    return ProjectDetailsOut.of(project)


@router.put("/projects/{project_id}/photo")
def upload_photo(
    project_id: int,
    photo: UploadFile,
    session: SessionDep,
    settings: SettingsDep,
    user: TeacherOrSuperuserDep,
) -> ProjectDetailsOut:
    # One byte more than allowed is enough to know a file is too large.
    data = photo.file.read(photos.MAX_BYTES + 1)
    project = photos.save_photo(
        session, settings.photos_dir, project_id, data, photo.content_type or ""
    )
    return ProjectDetailsOut.of(project)


@router.delete("/projects/{project_id}/photo")
def remove_photo(
    project_id: int,
    session: SessionDep,
    settings: SettingsDep,
    user: TeacherOrSuperuserDep,
) -> ProjectDetailsOut:
    project = photos.remove_photo(session, settings.photos_dir, project_id)
    return ProjectDetailsOut.of(project)


@router.get("/projects/{project_id}/photo")
def get_photo(
    project_id: int, session: SessionDep, settings: SettingsDep, user: CurrentUserDep
) -> Response:
    data, media_type = photos.read_photo(session, settings.photos_dir, project_id, user)
    return Response(content=data, media_type=media_type)


@router.post("/projects/{project_id}/members")
def add_member(
    project_id: int, body: MemberIn, session: SessionDep, user: TeacherOrSuperuserDep
) -> ProjectDetailsOut:
    project = memberships.add_member(
        session, project_id, body.student_id, confirm_move=body.confirm_move
    )
    return ProjectDetailsOut.of(project)


@router.delete("/projects/{project_id}/members/{student_id}")
def remove_member(
    project_id: int, student_id: int, session: SessionDep, user: TeacherOrSuperuserDep
) -> ProjectDetailsOut:
    project = memberships.remove_member(session, project_id, student_id)
    return ProjectDetailsOut.of(project)
