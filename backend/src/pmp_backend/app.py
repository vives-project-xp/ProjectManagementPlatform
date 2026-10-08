from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import sessionmaker

from pmp_backend.api import (
    auth,
    dev_login,
    programmes,
    projects,
    students,
    users,
)
from pmp_backend.database import is_reachable, make_engine
from pmp_backend.errors import Conflict, Forbidden, NotFound, Refused
from pmp_backend.services.seeding import seed_starting_accounts
from pmp_backend.settings import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    engine = make_engine(settings.database_url)
    make_session = sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        with make_session() as session:
            seed_starting_accounts(session, settings.logins_file)
        yield
        engine.dispose()

    app = FastAPI(title="VIVES Project Management Platform API", lifespan=lifespan)
    app.state.settings = settings
    app.state.sessionmaker = make_session
    app.include_router(auth.router)
    app.include_router(users.router)
    app.include_router(programmes.router)
    app.include_router(projects.router)
    app.include_router(students.router)
    if settings.dev_login:
        app.include_router(dev_login.router)

    @app.exception_handler(Refused)
    def refused(request: Request, error: Refused) -> JSONResponse:
        # Services refuse with a message fit to show; only the status differs.
        if isinstance(error, NotFound):
            code = status.HTTP_404_NOT_FOUND
        elif isinstance(error, Forbidden):
            code = status.HTTP_403_FORBIDDEN
        elif isinstance(error, Conflict):
            code = status.HTTP_409_CONFLICT
        else:
            code = status.HTTP_422_UNPROCESSABLE_CONTENT
        body = {"detail": str(error)}
        if error.code:
            body["code"] = error.code
        return JSONResponse(body, status_code=code)

    @app.get("/api/health")
    def health() -> JSONResponse:
        if is_reachable(engine):
            return JSONResponse({"status": "ok", "database": "ok"})
        return JSONResponse(
            {"status": "degraded", "database": "unreachable"}, status_code=503
        )

    return app
