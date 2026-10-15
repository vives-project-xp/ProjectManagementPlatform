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
    # The dedicated Trello account that owns every Project's Workspace and board
    # (spec #61). Only in /opt/pmp/.env.
    trello_api_key: str | None = None
    trello_token: str | None = None
    trello_api_url: str = "https://api.trello.com/1"
    # The mailbox for the 08:30 daily email (spec #68); without SMTP_HOST no
    # email is sent. Only in /opt/pmp/.env.
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    mail_from: str = "VIVES Project Experience <noreply@pmp.local>"
    # The address of the site, for links in emails.
    site_url: str = "https://10.20.10.33"
