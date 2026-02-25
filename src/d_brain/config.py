"""Application configuration using Pydantic Settings."""

import importlib.util
import sys
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
    openai_api_key: str = Field(
        default="",
        description="OpenAI API key for primary reasoning routes.",
    )
    openai_main_model: str = Field(
        default="gpt-5",
        description="Primary OpenAI model for main reasoning tasks.",
    )
    openai_utility_model: str = Field(
        default="gpt-5-mini",
        description="OpenAI model for utility-task fallback when local provider is unavailable.",
    )
    local_utility_model_ref: str = Field(
        default="utility:heuristic",
        description="Local utility model reference used in routing diagnostics.",
    )
    model_route_main_reasoning_provider: str = Field(
        default="openai",
        description="Provider for main reasoning tasks.",
    )
    model_route_voice_reasoning_provider: str = Field(
        default="openai",
        description="Provider for voice reasoning reply tasks.",
    )
    model_route_heartbeat_provider: str = Field(
        default="local",
        description="Provider for heartbeat utility tasks.",
    )
    model_route_cron_summary_provider: str = Field(
        default="local",
        description="Provider for cron summary utility tasks.",
    )
    model_route_light_classification_provider: str = Field(
        default="local",
        description="Provider for lightweight classification/parsing tasks.",
    )
    model_route_command_status_provider: str = Field(
        default="deterministic",
        description="Provider for command status/help routes; usually deterministic.",
    )
    model_route_allow_local_to_openai_fallback: bool = Field(
        default=True,
        description="Allow local utility routes to fall back to OpenAI when local is unavailable.",
    )
    model_route_allow_openai_to_local_fallback: bool = Field(
        default=False,
        description="Allow OpenAI routes to fall back to local only when explicitly enabled.",
    )
    model_route_force_openai_unavailable: bool = Field(
        default=False,
        description="Dev/test switch to simulate OpenAI unavailability in routing decisions.",
    )
    model_route_force_local_unavailable: bool = Field(
        default=False,
        description="Dev/test switch to simulate local provider unavailability in routing decisions.",
    )
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
    tts_deepgram_encoding: str = Field(
        default="opus",
        description="Deepgram TTS encoding (default: opus).",
    )
    tts_deepgram_container: str = Field(
        default="ogg",
        description="Deepgram TTS container (default: ogg).",
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
    telegram_disabled: bool = Field(
        default=True,
        validation_alias="D_BRAIN_TELEGRAM_DISABLED",
        description="Disable aiogram polling (useful when another gateway polls Telegram).",
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
    heartbeat_state_path: Path = Field(
        default=Path("./data/heartbeat_state.json"),
        description="Path to lightweight heartbeat/cron state file.",
    )
    scheduler_heartbeat_interval_minutes_default: int = Field(
        default=30,
        description="Default heartbeat cron interval in minutes.",
    )
    scheduler_heartbeat_enabled_default: bool = Field(
        default=True,
        description="Default enabled flag for heartbeat tick schedule.",
    )
    scheduler_digest_enabled_default: bool = Field(
        default=False,
        description="Default enabled flag for digest daily schedule.",
    )
    scheduler_digest_daily_time_default: str = Field(
        default="09:30",
        description="Default local HH:MM for daily digest schedule.",
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


def validate_settings(settings: Settings) -> tuple[list[str], list[str]]:
    """Return (errors, warnings) for current settings."""
    errors: list[str] = []
    warnings: list[str] = []

    if not settings.telegram_disabled and not settings.telegram_bot_token.strip():
        errors.append("TELEGRAM_BOT_TOKEN is required to start the bot.")

    if not settings.allow_all_users and not settings.allowed_user_ids:
        warnings.append(
            "No ALLOWED_USER_IDS configured and ALLOW_ALL_USERS is false; all users will be blocked."
        )

    if settings.stt_provider.strip().lower() == "deepgram":
        if importlib.util.find_spec("deepgram") is None:
            warnings.append("deepgram-sdk is not installed; STT will be unavailable.")
        if not settings.deepgram_api_key.strip():
            warnings.append("DEEPGRAM_API_KEY is empty; STT will be unavailable.")

    tts_provider = settings.tts_provider.strip().lower()
    if tts_provider not in {"", "none", "mock", "deepgram"}:
        warnings.append(
            f"Unsupported TTS_PROVIDER '{settings.tts_provider}'. Falling back to text."
        )
    if tts_provider == "deepgram":
        if not settings.deepgram_api_key.strip():
            warnings.append("DEEPGRAM_API_KEY is empty; TTS will be unavailable.")

    if settings.sidecar_payload_limit_bytes <= 0:
        errors.append("SIDECAR_PAYLOAD_LIMIT_BYTES must be positive.")
    if settings.scheduler_heartbeat_interval_minutes_default <= 0:
        errors.append("SCHEDULER_HEARTBEAT_INTERVAL_MINUTES_DEFAULT must be positive.")

    providers = {"openai", "local", "deterministic"}
    provider_fields = {
        "MODEL_ROUTE_MAIN_REASONING_PROVIDER": settings.model_route_main_reasoning_provider,
        "MODEL_ROUTE_VOICE_REASONING_PROVIDER": settings.model_route_voice_reasoning_provider,
        "MODEL_ROUTE_HEARTBEAT_PROVIDER": settings.model_route_heartbeat_provider,
        "MODEL_ROUTE_CRON_SUMMARY_PROVIDER": settings.model_route_cron_summary_provider,
        "MODEL_ROUTE_LIGHT_CLASSIFICATION_PROVIDER": settings.model_route_light_classification_provider,
        "MODEL_ROUTE_COMMAND_STATUS_PROVIDER": settings.model_route_command_status_provider,
    }
    for env_name, value in provider_fields.items():
        lowered = value.strip().lower()
        if lowered not in providers:
            warnings.append(
                f"{env_name} has unsupported value '{value}'. Using default routing policy."
            )

    if settings.model_route_main_reasoning_provider.strip().lower() == "openai":
        if not settings.openai_api_key.strip():
            warnings.append("OPENAI_API_KEY is empty; main reasoning routes may be unavailable.")
    if settings.model_route_voice_reasoning_provider.strip().lower() == "openai":
        if not settings.openai_api_key.strip():
            warnings.append("OPENAI_API_KEY is empty; voice reasoning routes may be unavailable.")

    if sys.version_info < (3, 12):
        errors.append("Python 3.12+ is required. Recreate the venv with Python 3.12.")

    return errors, warnings
