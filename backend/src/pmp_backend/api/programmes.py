from fastapi import APIRouter

from pmp_backend.api.deps import CurrentUserDep
from pmp_backend.domain import Programme

router = APIRouter(prefix="/api/programmes", tags=["programmes"])


@router.get("")
def programmes(user: CurrentUserDep) -> list[str]:
    """The Programmes to choose from in forms (a fixed list for now, ADR 0004)."""
    return [programme.value for programme in Programme]
