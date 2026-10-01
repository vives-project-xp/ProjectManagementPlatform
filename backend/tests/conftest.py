import os

import pytest

from pmp_backend.settings import Settings

# Tests run against a real PostgreSQL (docs/coding-standards.md). Locally that is
# the database from compose.test.yml; in CI a PostgreSQL service container.
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://pmp:pmp@localhost:5433/pmp_test",
)


@pytest.fixture
def settings() -> Settings:
    return Settings(database_url=TEST_DATABASE_URL)
