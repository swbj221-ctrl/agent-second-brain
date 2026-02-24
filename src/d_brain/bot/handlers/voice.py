"""Voice message handler."""

import logging
from datetime import datetime

from aiogram import Bot, Router
from aiogram.types import BufferedInputFile, Message

from d_brain.config import get_settings
from d_brain.services.english_tutor import EnglishTutorService, get_active_tutor_session
from d_brain.services.reflection_voice import (
    ReflectionVoiceService,
    get_active_reflection_session,
)
from d_brain.services.session import SessionStore
from d_brain.services.storage import VaultStorage
from d_brain.services.transcription import build_stt_adapter
from d_brain.services.tts import build_tts_adapter

router = Router(name="voice")
logger = logging.getLogger(__name__)
INTERNAL_ERROR_MESSAGE = "Временная ошибка. Попробуйте позже."


@router.message(lambda m: m.voice is not None)
async def handle_voice(message: Message, bot: Bot) -> None:
    """Handle voice messages."""
    if not message.voice or not message.from_user:
        return

    await message.chat.do(action="typing")

    settings = get_settings()
    stt = build_stt_adapter(settings)
    tts = build_tts_adapter(settings)
    reflection_service = ReflectionVoiceService()
    tutor_service = EnglishTutorService()

    try:
        file = await bot.get_file(message.voice.file_id)
        if not file.file_path:
            await message.answer("Не удалось скачать голосовое сообщение")
            return

        file_bytes = await bot.download_file(file.file_path)
        if not file_bytes:
            await message.answer("Не удалось скачать голосовое сообщение")
            return

        audio_bytes = file_bytes.read()
        reflection_state = get_active_reflection_session(message.from_user.id)
        if reflection_state:
            stt_result = await stt.transcribe(audio_bytes, language=settings.stt_language_default)
            if not stt_result.ok:
                await message.answer(
                    stt_result.error_message or "STT недоступен. Попробуйте текст."
                )
                return
            transcript = stt_result.text.strip()
            if not transcript:
                await message.answer("Не удалось распознать аудио.")
                return
            reply_text, error = await reflection_service.handle_user_turn(
                message.from_user.id, transcript
            )
            if error:
                await message.answer(error)
                return
            tts_result = await tts.speak(reply_text or "", voice=settings.tts_voice)
            if tts_result.ok and tts_result.audio_bytes:
                voice_file = BufferedInputFile(
                    tts_result.audio_bytes, filename="tutor-reply.ogg"
                )
                await message.answer_voice(voice=voice_file)
            else:
                await message.answer(reply_text or "")
            return

        tutor_state = get_active_tutor_session(message.from_user.id)
        if tutor_state:
            stt_result = await stt.transcribe(audio_bytes, language="en")
            if not stt_result.ok:
                await message.answer(
                    stt_result.error_message or "STT недоступен. Попробуйте текст."
                )
                return
            transcript = stt_result.text.strip()
            if not transcript:
                await message.answer("Не удалось распознать аудио.")
                return
            reply_text, error = await tutor_service.handle_user_turn(
                message.from_user.id, transcript
            )
            if error:
                await message.answer(error)
                return
            tts_result = await tts.speak(reply_text or "", voice=settings.tts_voice)
            if tts_result.ok and tts_result.audio_bytes:
                voice_file = BufferedInputFile(
                    tts_result.audio_bytes, filename="tutor-reply.ogg"
                )
                await message.answer_voice(voice=voice_file)
            else:
                await message.answer(reply_text or "")
            return

        stt_result = await stt.transcribe(audio_bytes, language=settings.stt_language_default)
        if not stt_result.ok:
            await message.answer(stt_result.error_message or "Не удалось распознать аудио")
            return
        transcript = stt_result.text.strip()
        if not transcript:
            await message.answer("Не удалось распознать аудио")
            return

        storage = VaultStorage(settings.vault_path)
        timestamp = datetime.fromtimestamp(message.date.timestamp())
        storage.append_to_daily(transcript, timestamp, "[voice]")

        session = SessionStore(settings.vault_path)
        session.append(
            message.from_user.id,
            "voice",
            text=transcript,
            duration=message.voice.duration,
            msg_id=message.message_id,
        )

        await message.answer(f"СЂСџР‹В¤ {transcript}\n\nРІСљвЂњ Р РЋР С•РЎвЂ¦РЎР‚Р В°Р Р…Р ВµР Р…Р С•")
        logger.info("Voice message saved: %d chars", len(transcript))

    except Exception:
        logger.exception("Error processing voice message")
        await message.answer(INTERNAL_ERROR_MESSAGE)
