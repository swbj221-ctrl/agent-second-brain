"""Command handlers for /status (DEV transport only)."""

from datetime import date

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from d_brain.bot.text_utils import safe_answer
from d_brain.config import get_settings
from d_brain.ux_actions import build_status_text
from d_brain.services.session import SessionStore
from d_brain.services.storage import VaultStorage

router = Router(name="commands")


@router.message(Command("status"))
async def cmd_status(message: Message) -> None:
    """Handle /status command."""
    user_id = message.from_user.id if message.from_user else 0
    settings = get_settings()
    storage = VaultStorage(settings.vault_path)

    # Log command
    session = SessionStore(settings.vault_path)
    session.append(user_id, "command", cmd="/status")

    await safe_answer(message, build_status_text(settings, user_id))


async def cmd_help(message: Message) -> None:
    """Handle /help command (delegates to telegram UX)."""
    from d_brain.bot.handlers.telegram_ux import cmd_help as ux_cmd_help

    await ux_cmd_help(message)
