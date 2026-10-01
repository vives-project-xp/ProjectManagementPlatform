"""FastAPI dependencies: database session and the logged-in User."""

from collections.abc import Callable, Iterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from pmp_backend.domain import Role
from pmp_backend.models import User
from pmp_backend.security import read_token
from pmp_backend.settings import Settings

_bearer = HTTPBearer(auto_error=False)


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_session(request: Request) -> Iterator[Session]:
    with request.app.state.sessionmaker() as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Your session has expired. Please log in again.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def current_user_allowing_temporary_password(
    session: SessionDep,
    settings: Annotated[Settings, Depends(get_settings)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    """The logged-in, active User, even if they still have a Temporary password."""
    if credentials is None:
        raise _unauthorized()
    user_id = read_token(credentials.credentials, settings.jwt_secret)
    user = session.get(User, user_id) if user_id is not None else None
    # Checked on every request, so deactivating a User ends their session at once.
    if user is None or not user.is_active:
        raise _unauthorized()
    return user


def current_user(
    user: Annotated[User, Depends(current_user_allowing_temporary_password)],
) -> User:
    """The logged-in User, refused while they must still change their password."""
    if user.must_change_password:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You must change your password first.",
        )
    return user


def _role_in(*roles: Role) -> Callable[[User], User]:
    """A dependency giving the logged-in User, refused without one of `roles`."""

    def check(user: Annotated[User, Depends(current_user)]) -> User:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have access to this.",
            )
        return user

    return check


TemporaryPasswordUserDep = Annotated[
    User, Depends(current_user_allowing_temporary_password)
]
CurrentUserDep = Annotated[User, Depends(current_user)]
SuperuserDep = Annotated[User, Depends(_role_in(Role.SUPERUSER))]
# Teachers and the Superuser: everything about Projects and Members (spec #3).
StaffDep = Annotated[User, Depends(_role_in(Role.SUPERUSER, Role.TEACHER))]
