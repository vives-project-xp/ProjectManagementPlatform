from pydantic import ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Frontend configuration, read from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Where the frontend reaches the backend's REST API (ADR 0003).
    backend_url: str = "http://localhost:8000"
    # Signs the browser session cookie that holds the login token.
    storage_secret: str
    # Send that cookie only over HTTPS (production, behind Caddy). Off for tests
    # and plain-HTTP local runs.
    secure_cookies: bool = False

    # The footer on every page (#76, #79): VIVES' accounts as linked on vives.be,
    # the privacy policy and the campus address. Empty keeps the default (Compose
    # passes unset ones as empty); "none" hides that part of the footer.
    footer_instagram: str = "https://www.instagram.com/viveshogeschool"
    footer_tiktok: str = "https://www.tiktok.com/@viveshogeschool"
    footer_youtube: str = "https://www.youtube.com/vivesvideo"
    footer_linkedin: str = "https://www.linkedin.com/school/vives/"
    footer_privacy_url: str = "https://www.vives.be/nl/over-vives/privacyverklaring"
    footer_address: str = (
        "VIVES Brugge Xaverianenstraat · Xaverianenstraat 10, 8200 Brugge"
    )

    @field_validator(
        "footer_instagram",
        "footer_tiktok",
        "footer_youtube",
        "footer_linkedin",
        "footer_privacy_url",
        "footer_address",
        mode="before",
    )
    @classmethod
    def _empty_is_default(cls, value: str, info: ValidationInfo) -> str:
        if value == "":
            return cls.model_fields[info.field_name].default
        return "" if value.strip().lower() == "none" else value
