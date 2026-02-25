"""Text helpers for Telegram UX."""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)
CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
MOJIBAKE_HINTS = ("Р", "С", "Ð", "Ñ")


def _cyrillic_score(text: str) -> int:
    return len(CYRILLIC_RE.findall(text))


def fix_mojibake(text: str) -> str:
    if not text:
        return text
    if not any(hint in text for hint in MOJIBAKE_HINTS):
        return text
    try:
        candidate = text.encode("cp1251").decode("utf-8")
    except Exception:
        return text
    if _cyrillic_score(candidate) > _cyrillic_score(text):
        logger.warning("Possible mojibake detected; applying fix")
        return candidate
    return text


async def safe_answer(message, text: str, **kwargs):
    return await message.answer(fix_mojibake(text), **kwargs)
