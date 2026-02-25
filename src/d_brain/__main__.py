"""Entry point for running d-brain as a module."""

import asyncio
import logging
import os
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


def _env_true(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


async def main() -> None:
    """Main entry point."""
    from pydantic import ValidationError

    from d_brain.config import get_settings, validate_settings

    try:
        settings = get_settings()
    except ValidationError as exc:
        logger.error("Invalid configuration. Fix .env values and retry.")
        logger.error("%s", exc)
        raise SystemExit(2)

    errors, warnings = validate_settings(settings)
    for warning in warnings:
        logger.warning(warning)
    if errors:
        for err in errors:
            logger.error(err)
        raise SystemExit(2)

    logger.info("d-brain starting...")
    logger.info("Vault path: %s", settings.vault_path)
    logger.info("Allowed users: %s", settings.allowed_user_ids or "all")
    logger.info(
        "Startup mode: telegram_transport=%s aiogram_polling_disabled=%s",
        "openclaw" if settings.telegram_disabled else "local_aiogram_requested",
        bool(settings.telegram_disabled),
    )
    if settings.telegram_disabled:
        logger.info(
            "Telegram transport is handled by OpenClaw. aiogram polling is disabled by default."
        )
        return

    if not _env_true("D_BRAIN_ALLOW_LOCAL_POLLING"):
        logger.error(
            "Local aiogram polling start blocked by OpenClaw-first guardrail. "
            "Set D_BRAIN_TELEGRAM_DISABLED=1 for production/OpenClaw transport, "
            "or set D_BRAIN_ALLOW_LOCAL_POLLING=1 only for local debugging."
        )
        logger.info("No-conflict mode: exiting before aiogram polling starts.")
        return

    from d_brain.bot.main import run_bot
    await run_bot(settings)


if __name__ == "__main__":
    if sys.version_info < (3, 12):
        logger.error("Python 3.12+ is required. Recreate the venv with Python 3.12.")
        raise SystemExit(2)
    asyncio.run(main())
