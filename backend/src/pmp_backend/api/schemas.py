"""Response bodies shared by several routers."""

from pydantic import BaseModel, ConfigDict

from pmp_backend.models import User


class PersonOut(BaseModel):
    id: int
    name: str

    @classmethod
    def of(cls, user: User) -> "PersonOut":
        return cls(id=user.id, name=user.full_name)


class ProjectRefOut(BaseModel):
    id: int
    title: str


class StudentOut(PersonOut):
    """A Student with the Project they are a Member of, if any."""

    programme: str | None
    year: str | None
    is_active: bool
    project: ProjectRefOut | None

    @classmethod
    def of(cls, user: User) -> "StudentOut":
        project = user.project
        return cls(
            **PersonOut.of(user).model_dump(),
            programme=user.programme,
            year=user.year,
            is_active=user.is_active,
            project=ProjectRefOut(id=project.id, title=project.title)
            if project
            else None,
        )


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    first_name: str
    last_name: str
    email: str
    role: str
    is_active: bool
    must_change_password: bool
    programme: str | None
    year: str | None
