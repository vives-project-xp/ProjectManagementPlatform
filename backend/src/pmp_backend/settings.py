from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    """Just the database connection, for tools such as migrations."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str


class Settings(DatabaseSettings):
    """Backend configuration, read from environment variables."""

    jwt_secret: str
    token_lifetime_minutes: int = 8 * 60
    # Starting accounts (role,email,password per line); created once if missing.
    logins_file: Path | None = None
    # Project photos, one file per Project; a Docker volume in production.
    photos_dir: Path = Path("/data/photos")
    # Test login: log in as any active User without a password. For the team's
    # testing only; off unless DEV_LOGIN=true.
    dev_login: bool = False
    # The GitHub organisation that gets the Project repositories, and a
    # fine-grained token for it (spec #49). Only in /opt/pmp/.env.
    github_org: str | None = None
    github_token: str | None = None
    github_api_url: str = "https://api.github.com"
