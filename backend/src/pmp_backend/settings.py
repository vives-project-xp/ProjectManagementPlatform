from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Backend configuration, read from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    jwt_secret: str
    token_lifetime_minutes: int = 8 * 60
    # Starting accounts (role,email,password per line); created once if missing.
    logins_file: Path | None = None
