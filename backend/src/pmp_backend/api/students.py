from fastapi import APIRouter

from pmp_backend.api.deps import SessionDep, TeacherOrSuperuserDep
from pmp_backend.api.schemas import StudentOut
from pmp_backend.domain import Year
from pmp_backend.services import users

router = APIRouter(prefix="/api/students", tags=["students"])


@router.get("")
def students(
    session: SessionDep,
    user: TeacherOrSuperuserDep,
    without_project: bool = False,
    programme: str | None = None,
    year: Year | None = None,
) -> list[StudentOut]:
    """All Students with their Project, for the Members screen and the add form."""
    found = users.list_students(
        session, without_project=without_project, programme=programme, year=year
    )
    return [StudentOut.of(student) for student in found]
