"""Database helpers shared by the backend and frontend test suites."""

import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://pmp:pmp@localhost:5433/pmp_test",
)

_ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


def migrate(database_url: str = TEST_DATABASE_URL) -> None:
    """Bring the test database to the latest migration."""
    os.environ["DATABASE_URL"] = database_url
    command.upgrade(Config(str(_ALEMBIC_INI)), "head")


def reset(database_url: str = TEST_DATABASE_URL) -> None:
    """Empty every table so each test starts from a clean database."""
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE projects, users RESTART IDENTITY CASCADE"))
    engine.dispose()
