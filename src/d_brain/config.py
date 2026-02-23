"""Application configuration using Pydantic Settings."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    telegram_bot_token: str = Field(description="Telegram Bot API token")
    deepgram_api_key: str = Field(
        default="",
        description="Deepgram API key for transcription (required for voice/STT only).",
    )
    stt_provider: str = Field(
        default="deepgram",
        description="STT provider name (default: deepgram).",
    )
    stt_language_default: str = Field(
        default="ru",
        description="Default STT language code for non-tutor voice capture.",
    )
    stt_deepgram_model: str = Field(
        default="nova-3",
        description="Deepgram model name for STT.",
    )
    tts_provider: str = Field(
        default="none",
        description="TTS provider name (default: none).",
    )
    tts_voice: str = Field(
        default="",
        description="Default TTS voice name.",
    )
    todoist_api_key: str = Field(default="", description="Todoist API key for tasks")
    vault_path: Path = Field(
        default=Path("./vault"),
        description="Path to Obsidian vault directory",
    )
    db_path: Path = Field(
        default=Path("./data/app.db"),
        description="Path to SQLite database file",
    )
    migrations_path: Path = Field(
        default=Path("./deploy/migrations"),
        description="Path to SQL migration files",
    )
    allowed_user_ids: list[int] = Field(
        default_factory=list,
        description="List of Telegram user IDs allowed to use the bot",
    )
    allow_all_users: bool = Field(
        default=False,
        description="Whether to allow access to all users (security risk!)",
    )
    sidecar_payload_limit_bytes: int = Field(
        default=32_768,
        description="Max JSON payload size for sidecar requests in bytes.",
    )
    backup_dir: Path = Field(
        default=Path("./data/backups"),
        description="Directory where database backups are stored.",
    )
    backup_prefix: str = Field(
        default="db_backup",
        description="Filename prefix for database backups.",
    )
    backup_retention: int = Field(
        default=6,
        description="How many recent backups to keep (rotation).",
    )
    backup_snapshot_enabled: bool = Field(
        default=True,
        description="Whether to create a project snapshot ZIP alongside DB backups.",
    )
    backup_snapshot_paths: list[str] = Field(
        default_factory=lambda: ["docs"],
        description="Project-relative paths to include in backup snapshot ZIP.",
    )

    @property
    def daily_path(self) -> Path:
        """Path to daily notes directory."""
        return self.vault_path / "daily"

    @property
    def attachments_path(self) -> Path:
        """Path to attachments directory."""
        return self.vault_path / "attachments"

    @property
    def thoughts_path(self) -> Path:
        """Path to thoughts directory."""
        return self.vault_path / "thoughts"


def get_settings() -> Settings:
    """Get application settings instance."""
    return Settings()
