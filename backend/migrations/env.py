from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from pmp_backend.models import Base
from pmp_backend.settings import DatabaseSettings

config = context.config
# Migrations only need the database; the rest of Settings is not required here.
config.set_main_option("sqlalchemy.url", DatabaseSettings().database_url)

if config.config_file_name is not None:
    # Keep the app's loggers working when migrations run in-process (tests).
    fileConfig(config.config_file_name, disable_existing_loggers=False)


target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
