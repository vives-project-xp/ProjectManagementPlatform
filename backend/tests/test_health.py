from fastapi.testclient import TestClient

from pmp_backend.app import create_app
from pmp_backend.settings import Settings


def test_health_reports_ok_when_database_is_reachable(settings: Settings):
    client = TestClient(create_app(settings))

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_health_reports_unavailable_when_database_is_unreachable():
    # Nothing listens on port 1, so the connection is refused immediately.
    settings = Settings(
        database_url="postgresql+psycopg://pmp:pmp@127.0.0.1:1/pmp?connect_timeout=2",
        jwt_secret="unused-in-this-test-but-required-by-settings",
    )
    client = TestClient(create_app(settings))

    response = client.get("/api/health")

    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "database": "unreachable"}
