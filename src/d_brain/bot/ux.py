"""Telegram UX helpers."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

from aiogram.types import Message

logger = logging.getLogger(__name__)
T = TypeVar("T")


def format_user_error(reason: str | None = None) -> str:
    """Return a safe, short error message for users."""
    base = "❓ Не удалось выполнить команду."
    if reason:
        base = f"{base}\nПричина: {reason}."
    return f"{base}\nПопробуй еще раз через минуту."



async def run_with_ack(
    message: Message,
    ack_text: str,
    work: Callable[[], Awaitable[T]],
) -> T | None:
    """Send ack + typing, run work, and report safe error on failure."""
    await message.answer(ack_text)
    try:
        if message.chat:
            await message.chat.do(action="typing")
    except Exception:
        pass
    try:
        return await work()
    except Exception:
        logger.exception("Telegram handler failed")
        await message.answer(format_user_error())
        return None
