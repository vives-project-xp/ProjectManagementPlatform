from fastapi import APIRouter

from pmp_backend.api.deps import SessionDep, TeacherOrSuperuserDep
from pmp_backend.api.schemas import StudentOut
from pmp_backend.services import users

router = APIRouter(prefix="/api/students", tags=["students"])


@router.get("")
def students(session: SessionDep, user: TeacherOrSuperuserDep) -> list[StudentOut]:
    """All Students with their Project (filters arrive with #11)."""
    return [StudentOut.of(student) for student in users.list_students(session)]
