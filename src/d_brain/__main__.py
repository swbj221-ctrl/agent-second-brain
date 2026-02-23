"""Entry point for running d-brain as a module."""

import asyncio
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


async def main() -> None:
    """Main entry point."""
    from pydantic import ValidationError

    from d_brain.bot.main import run_bot
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

    await run_bot(settings)


if __name__ == "__main__":
    if sys.version_info < (3, 12):
        logger.error("Python 3.12+ is required. Recreate the venv with Python 3.12.")
        raise SystemExit(2)
    asyncio.run(main())
