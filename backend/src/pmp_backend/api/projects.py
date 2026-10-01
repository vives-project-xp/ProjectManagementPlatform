from typing import Annotated

from fastapi import APIRouter, status
from pydantic import BaseModel, Field, StringConstraints

from pmp_backend.api.deps import SessionDep, TeacherOrSuperuserDep
from pmp_backend.models import Project, User
from pmp_backend.services import projects
from pmp_backend.services.projects import ProjectFields

router = APIRouter(prefix="/api", tags=["projects"])


class PersonOut(BaseModel):
    id: int
    name: str

    @classmethod
    def of(cls, user: User) -> "PersonOut":
        return cls(id=user.id, name=f"{user.first_name} {user.last_name}")


class ProjectOut(BaseModel):
    id: int
    title: str
    description: str | None
    product_owner: PersonOut
    team_size_min: int
    team_size_max: int
    status: str

    @classmethod
    def of(cls, project: Project) -> "ProjectOut":
        return cls(
            id=project.id,
            title=project.title,
            description=project.description,
            product_owner=PersonOut.of(project.product_owner),
            team_size_min=project.team_size_min,
            team_size_max=project.team_size_max,
            status=project.status,
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


@router.get("/teachers")
def teachers(session: SessionDep, user: TeacherOrSuperuserDep) -> list[PersonOut]:
    """The active Teachers, to choose a Product Owner from."""
    return [PersonOut.of(teacher) for teacher in projects.active_teachers(session)]


@router.get("/projects")
def list_projects(session: SessionDep, user: TeacherOrSuperuserDep) -> list[ProjectOut]:
    return [ProjectOut.of(project) for project in projects.list_projects(session)]


@router.post("/projects", status_code=status.HTTP_201_CREATED)
def create_project(
    body: ProjectIn, session: SessionDep, user: TeacherOrSuperuserDep
) -> ProjectOut:
    return ProjectOut.of(projects.create_project(session, body.fields()))


@router.get("/projects/{project_id}")
def get_project(
    project_id: int, session: SessionDep, user: TeacherOrSuperuserDep
) -> ProjectOut:
    return ProjectOut.of(projects.get_project(session, project_id))


@router.put("/projects/{project_id}")
def update_project(
    project_id: int, body: ProjectIn, session: SessionDep, user: TeacherOrSuperuserDep
) -> ProjectOut:
    return ProjectOut.of(projects.update_project(session, project_id, body.fields()))
