"""Text message handler."""

import logging
from datetime import datetime

from aiogram import Router
from aiogram.types import Message

from d_brain.config import get_settings
from d_brain.services.english_tutor import EnglishTutorService, get_active_tutor_session
from d_brain.services.reflection_voice import (
    ReflectionVoiceService,
    get_active_reflection_session,
)
from d_brain.services.session import SessionStore
from d_brain.services.storage import VaultStorage

router = Router(name="text")
logger = logging.getLogger(__name__)
INTERNAL_ERROR_MESSAGE = "Р’СЂРµРјРµРЅРЅР°СЏ РѕС€РёР±РєР°. РџРѕРїСЂРѕР±СѓР№С‚Рµ РїРѕР·Р¶Рµ."
TRANSCRIPT_WARNING = (
    "Получил только авто-транскрипт Telegram (он может быть неточным). "
    "Лучше отправь обычное голосовое сообщение — тогда расшифрую точнее."
)


def _looks_like_auto_transcript(text: str) -> bool:
    normalized = text.strip().lower()
    return normalized.startswith("transcript:") or normalized.startswith("transcription:")


@router.message(lambda m: m.text is not None and not m.text.startswith("/"))
async def handle_text(message: Message) -> None:
    """Handle text messages (excluding commands)."""
    if not message.text or not message.from_user:
        return

    try:
        if _looks_like_auto_transcript(message.text):
            logger.info("Auto-transcript text received without media; path=transcript_fallback")
            await message.answer(TRANSCRIPT_WARNING)
            return

        reflection_state = get_active_reflection_session(message.from_user.id)
        if reflection_state:
            reflection_service = ReflectionVoiceService()
            reply_text, error = await reflection_service.handle_user_turn(
                message.from_user.id, message.text
            )
            if error:
                await message.answer(error)
                return
            await message.answer(reply_text or "")
            return

        tutor_state = get_active_tutor_session(message.from_user.id)
        if tutor_state:
            tutor_service = EnglishTutorService()
            reply_text, error = await tutor_service.handle_user_turn(
                message.from_user.id, message.text
            )
            if error:
                await message.answer(error)
                return
            await message.answer(reply_text or "")
            return

        settings = get_settings()
        storage = VaultStorage(settings.vault_path)

        timestamp = datetime.fromtimestamp(message.date.timestamp())
        storage.append_to_daily(message.text, timestamp, "[text]")

        # Log to session
        session = SessionStore(settings.vault_path)
        session.append(
            message.from_user.id,
            "text",
            text=message.text,
            msg_id=message.message_id,
        )

        await message.answer("вњ… РЎРѕС…СЂР°РЅРµРЅРѕ")
        logger.info("Text message saved: %d chars", len(message.text))
    except Exception:
        logger.exception("Error processing text message")
        await message.answer(INTERNAL_ERROR_MESSAGE)
