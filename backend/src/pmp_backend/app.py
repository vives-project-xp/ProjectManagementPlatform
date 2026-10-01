from fastapi import FastAPI
from fastapi.responses import JSONResponse

from pmp_backend.database import is_reachable, make_engine
from pmp_backend.settings import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    engine = make_engine(settings.database_url)

    app = FastAPI(title="VIVES Project Management Platform API")

    @app.get("/api/health")
    def health() -> JSONResponse:
        if is_reachable(engine):
            return JSONResponse({"status": "ok", "database": "ok"})
        return JSONResponse(
            {"status": "degraded", "database": "unreachable"}, status_code=503
        )

    return app
