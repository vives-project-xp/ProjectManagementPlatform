from pathlib import Path

from pydantic import SecretStr
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
    # Photos and files attached to Chat messages; a Docker volume in production.
    chat_files_dir: Path = Path("/data/chat-files")
    # Photos and videos of Weekly updates (spec #110), one folder per Project.
    social_media_dir: Path = Path("/data/social-media")
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
    # The school's LLM for Post suggestions (spec #110, ADR 0009): a personal
    # key from the school's LiteLLM portal. Without a key, no suggestions.
    llm_base_url: str = "https://api.llm.mechatronics.be/v1"
    llm_model: str = "qwen3.8-27b"
    llm_api_key: SecretStr | None = None
    # Automatic publishing on Instagram (#117, ADR 0010): the team's Instagram
    # Business account (Instagram API with Instagram Login). INSTAGRAM_TOKEN is
    # its long-lived token, only the first one: refreshed tokens live in the
    # database. Without a token every post goes through To post today.
    instagram_token: SecretStr | None = None
    instagram_account_id: str = "me"
    # Apps made since 2026 get "Unified login": a token for graph.facebook.com
    # that never expires, with the account's id (1784…) as INSTAGRAM_ACCOUNT_ID
    # and INSTAGRAM_REFRESH_URL empty (no refresh); see docs/instagram.md.
    instagram_api_url: str = "https://graph.instagram.com/v23.0"
    instagram_refresh_url: str = "https://graph.instagram.com/refresh_access_token"
    # The public address Instagram downloads photos from (https://<host>), set
    # only once the VM is reachable from the internet; without it photo posts
    # go through To post today (Reels are uploaded directly).
    public_media_url: str | None = None
    # TikTok as a Channel (spec #145): the developer app's client key and
    # secret (developers.tiktok.com) and the redirect URI registered for Login
    # Kit. The Superuser connects the account on the Social media screen and
    # pastes the address TikTok redirects to; the account's tokens then live
    # in the database. Without a key and secret TikTok is off. See
    # docs/tiktok.md.
    tiktok_client_key: str | None = None
    tiktok_client_secret: SecretStr | None = None
    tiktok_redirect_uri: str = (
        "https://github.com/vives-project-xp/ProjectManagementPlatform"
    )
    tiktok_api_url: str = "https://open.tiktokapis.com"
    tiktok_auth_url: str = "https://www.tiktok.com/v2/auth/authorize/"
    # TikTok's URL-prefix verification (#150): the file name TikTok gives (e.g.
    # "tiktokAbC123.txt") and its content, served at PUBLIC_MEDIA_URL/social/
    # so TikTok accepts the Weekly slideshow's photo links from there.
    tiktok_verification_file: str | None = None
    tiktok_verification_content: str | None = None
    # The mailbox for the 08:30 daily email (spec #68); without SMTP_HOST no
    # email is sent. Only in /opt/pmp/.env.
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    mail_from: str = "VIVES Project Experience <noreply@pmp.local>"
    # The address of the site, for links in emails.
    site_url: str = "https://10.20.10.33"
