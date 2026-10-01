from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import SQLAlchemyError


def make_engine(database_url: str) -> Engine:
    return create_engine(database_url, pool_pre_ping=True)


def is_reachable(engine: Engine) -> bool:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return False
    return True
