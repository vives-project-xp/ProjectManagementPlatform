from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Frontend configuration, read from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Where the frontend reaches the backend's REST API (ADR 0003).
    backend_url: str = "http://localhost:8000"
    # Signs the browser session cookie that holds the login token.
    storage_secret: str
