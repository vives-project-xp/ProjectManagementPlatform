import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import sessionmaker

from pmp_backend.api import (
    auth,
    chat,
    dev_login,
    github,
    planning,
    programmes,
    projects,
    students,
    top3,
    trello,
    users,
)
from pmp_backend.database import is_reachable, make_engine
from pmp_backend.errors import Conflict, Forbidden, NotFound, Refused, Unavailable
from pmp_backend.services import daily_email, mail
from pmp_backend.services.auth import LoginGuard
from pmp_backend.services.chat import TypingBoard, clean_up_forever
from pmp_backend.services.github import HttpGitHub
from pmp_backend.services.seeding import seed_starting_accounts
from pmp_backend.services.trello import HttpTrello
from pmp_backend.settings import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    engine = make_engine(settings.database_url)
    make_session = sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        with make_session() as session:
            seed_starting_accounts(session, settings.logins_file)
        # The 08:30 Daily email, only with a mailbox configured (spec #68).
        sender = None
        if mail.is_configured(settings):
            sender = asyncio.create_task(
                daily_email.run_forever(make_session, app.state.mailer, settings)
            )
        # Archived Projects' Chats are deleted 6 months after archiving (#98).
        cleaner = asyncio.create_task(
            clean_up_forever(make_session, settings.chat_files_dir)
        )
        yield
        for task in (sender, cleaner):
            if task is not None:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
        engine.dispose()

    app = FastAPI(title="VIVES Project Management Platform API", lifespan=lifespan)
    app.state.settings = settings
    app.state.sessionmaker = make_session
    app.state.login_guard = LoginGuard()
    # "Is typing…" in the Chats (in memory, like the LoginGuard).
    app.state.chat_typing = TypingBoard()
    # Tests replace it with testing.FakeGitHub.
    app.state.github = HttpGitHub(settings)
    # Tests replace it with testing.FakeTrello.
    app.state.trello = HttpTrello(settings)
    # Tests replace it with testing.FakeMailer.
    app.state.mailer = mail.SmtpMailer(settings)
    app.include_router(auth.router)
    app.include_router(users.router)
    app.include_router(programmes.router)
    app.include_router(projects.router)
    app.include_router(students.router)
    app.include_router(top3.router)
    app.include_router(github.router)
    app.include_router(trello.router)
    app.include_router(planning.router)
    app.include_router(chat.router)
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
        elif isinstance(error, Unavailable):
            code = status.HTTP_503_SERVICE_UNAVAILABLE
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
