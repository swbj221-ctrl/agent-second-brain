"""Telegram delivery helpers for scheduled jobs."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

from d_brain.config import Settings

logger = logging.getLogger(__name__)
TELEGRAM_TIMEOUT_S = 15.0
TELEGRAM_MAX_RETRIES = 2
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


@dataclass(slots=True)
class TelegramSendResult:
    chat_id: int
    ok: bool
    message_id: int | None = None
    error: str | None = None


def send_telegram_message(
    bot_token: str,
    chat_id: int,
    text: str,
    parse_mode: str = "HTML",
    timeout_s: float = TELEGRAM_TIMEOUT_S,
) -> TelegramSendResult:
    if not bot_token:
        return TelegramSendResult(chat_id=chat_id, ok=False, error="Missing bot token")
    if not text.strip():
        return TelegramSendResult(chat_id=chat_id, ok=False, error="Empty message")
    try:
        import httpx  # lazy import to keep scheduler import-safe
    except Exception:
        return TelegramSendResult(
            chat_id=chat_id,
            ok=False,
            error="missing_dependency:httpx",
        )

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }
    last_error: str | None = None
    for attempt in range(TELEGRAM_MAX_RETRIES + 1):
        try:
            with httpx.Client(timeout=timeout_s) as client:
                response = client.post(url, data=payload)
            if response.status_code in RETRYABLE_STATUS:
                last_error = f"retryable_status:{response.status_code}"
                if attempt < TELEGRAM_MAX_RETRIES:
                    logger.warning(
                        "Telegram send retryable status %s (attempt %d)",
                        response.status_code,
                        attempt + 1,
                    )
                    time.sleep(0.5 * (attempt + 1))
                    continue
            data = response.json()
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last_error = str(exc)
            if attempt < TELEGRAM_MAX_RETRIES:
                logger.warning(
                    "Telegram send transient error (attempt %d): %s",
                    attempt + 1,
                    exc,
                )
                time.sleep(0.5 * (attempt + 1))
                continue
            return TelegramSendResult(chat_id=chat_id, ok=False, error=str(exc))
        except Exception as exc:
            return TelegramSendResult(chat_id=chat_id, ok=False, error=str(exc))
        break

    if not data.get("ok"):
        description = data.get("description") or "Unknown Telegram error"
        if last_error:
            description = f"{description} ({last_error})"
        return TelegramSendResult(chat_id=chat_id, ok=False, error=description)

    message_id = None
    result = data.get("result") or {}
    if isinstance(result, dict):
        message_id = result.get("message_id")

    return TelegramSendResult(chat_id=chat_id, ok=True, message_id=message_id)


def send_to_allowed_users(
    settings: Settings,
    text: str,
    parse_mode: str = "HTML",
) -> list[TelegramSendResult]:
    if not settings.allowed_user_ids:
        logger.warning("No allowed_user_ids configured for Telegram delivery.")
        return []
    results: list[TelegramSendResult] = []
    for chat_id in settings.allowed_user_ids:
        result = send_telegram_message(
            settings.telegram_bot_token,
            int(chat_id),
            text,
            parse_mode=parse_mode,
        )
        results.append(result)
    return results
