import os

import httpx
import pytest

from pmp_backend.app import create_app
from pmp_backend.settings import Settings
from pmp_frontend import api

pytest_plugins = ["nicegui.testing.user_plugin"]

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://pmp:pmp@localhost:5433/pmp_test",
)


@pytest.fixture(autouse=True)
def backend_in_process():
    """Route the frontend's API calls to the real backend app, in this process."""
    backend = create_app(Settings(database_url=TEST_DATABASE_URL))
    api.use_transport(httpx.ASGITransport(app=backend))
    yield
    api.use_transport(None)
