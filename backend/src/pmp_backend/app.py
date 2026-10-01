from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy.orm import sessionmaker

from pmp_backend.api import auth, programmes, projects, users
from pmp_backend.database import is_reachable, make_engine
from pmp_backend.services.projects import ProjectError
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
    app.add_exception_handler(ProjectError, projects.refused)

    @app.get("/api/health")
    def health() -> JSONResponse:
        if is_reachable(engine):
            return JSONResponse({"status": "ok", "database": "ok"})
        return JSONResponse(
            {"status": "degraded", "database": "unreachable"}, status_code=503
        )

    return app
