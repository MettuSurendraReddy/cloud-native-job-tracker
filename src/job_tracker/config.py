"""Application settings loaded from environment variables or a local .env file."""

from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for Gmail and Pub/Sub integrations."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    google_pubsub_subscription: str | None = None
    google_pubsub_topic: str | None = None
    google_application_credentials: Path | None = None
    google_sheets_spreadsheet_id: str | None = None
    google_sheets_worksheet: str = "Applications"
    gmail_user_id: str = "me"
    gmail_client_secrets_file: Path = Path("credentials.json")
    gmail_token_file: Path = Path("token.json")
    history_cursor_db: Path = Path("state/tracker.sqlite3")
    gemini_api_key: SecretStr | None = None
    groq_api_key: SecretStr | None = None
    gemini_model: str = "gemini-2.5-flash"
    groq_model: str = "llama-3.3-70b-versatile"
    llm_email_body_max_chars: int = Field(default=20_000, ge=1_000, le=100_000)
    neo4j_uri: str | None = None
    neo4j_username: str | None = None
    neo4j_password: SecretStr | None = None
    neo4j_mcp_username: str | None = None
    neo4j_mcp_password: SecretStr | None = None
    neo4j_database: str = "neo4j"

    @field_validator("gemini_api_key", "groq_api_key", mode="before")
    @classmethod
    def empty_api_keys_are_missing(cls, value):
        if isinstance(value, str) and not value.strip():
            return None
        return value


def get_settings() -> Settings:
    """Load settings at application startup."""

    return Settings()
