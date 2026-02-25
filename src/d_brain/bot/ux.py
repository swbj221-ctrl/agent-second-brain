"""Telegram UX helpers."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

from aiogram.types import Message

from d_brain.bot.text_utils import fix_mojibake, safe_answer

logger = logging.getLogger(__name__)
T = TypeVar("T")


def format_user_error(reason: str | None = None) -> str:
    """Return a safe, short error message for users."""
    base = "вќ“ РќРµ СѓРґР°Р»РѕСЃСЊ РІС‹РїРѕР»РЅРёС‚СЊ РєРѕРјР°РЅРґСѓ."
    if reason:
        base = f"{base}\nРџСЂРёС‡РёРЅР°: {reason}."
    return fix_mojibake(f"{base}\nРџРѕРїСЂРѕР±СѓР№ РµС‰Рµ СЂР°Р· С‡РµСЂРµР· РјРёРЅСѓС‚Сѓ.")


async def run_with_ack(
    message: Message,
    ack_text: str,
    work: Callable[[], Awaitable[T]],
) -> T | None:
    """Send ack + typing, run work, and report safe error on failure."""
    await safe_answer(message, ack_text)
    try:
        if message.chat:
            await message.chat.do(action="typing")
    except Exception:
        pass
    try:
        return await work()
    except Exception:
        logger.exception("Telegram handler failed")
        await safe_answer(message, format_user_error())
        return None
