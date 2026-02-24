"""Voice message handler."""

import logging
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from aiogram import Bot, Router
from aiogram.types import FSInputFile, Message

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
INTERNAL_ERROR_MESSAGE = "Р’СЂРµРјРµРЅРЅР°СЏ РѕС€РёР±РєР°. РџРѕРїСЂРѕР±СѓР№С‚Рµ РїРѕР·Р¶Рµ."
TTS_LOG_TRIM = 500
STT_DEFAULT_LANGUAGE = "ru"
STT_TUTOR_LANGUAGE = "en"
AUDIO_EXTENSIONS = {".ogg", ".m4a", ".mp3", ".wav"}


def _trim_log(value: str | None, limit: int = TTS_LOG_TRIM) -> str:
    if not value:
        return ""
    text = value.strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit]}...<trimmed>"


def _write_tts_audio(audio_bytes: bytes, label: str) -> Path:
    out_dir = Path("data") / "tts" / "telegram"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{label}_{uuid4().hex}.ogg"
    out_path.write_bytes(audio_bytes)
    return out_path


def _tts_command_label(provider: str) -> str:
    provider = provider.strip().lower()
    if provider == "deepgram":
        return "httpx"
    if provider in {"", "none"}:
        return "none"
    return provider


def _log_tts_diagnostics(
    provider: str,
    command_label: str,
    exit_code: int | None,
    stdout: str,
    stderr: str,
    output_path: Path | None,
    output_size: int,
    error_code: str | None,
    error_message: str | None,
) -> None:
    logger.info(
        "TTS generation: provider=%s command=%s exit_code=%s stdout=%s stderr=%s "
        "output_path=%s output_size=%s error_code=%s error_message=%s",
        provider,
        command_label,
        exit_code,
        _trim_log(stdout),
        _trim_log(stderr),
        str(output_path) if output_path else "",
        output_size,
        error_code or "",
        _trim_log(error_message),
    )


def _is_audio_document(doc: object) -> bool:
    mime_type = (getattr(doc, "mime_type", "") or "").lower()
    if mime_type.startswith("audio/"):
        return True
    file_name = (getattr(doc, "file_name", "") or "").lower()
    return any(file_name.endswith(ext) for ext in AUDIO_EXTENSIONS)


def _select_media(message: Message) -> dict[str, object] | None:
    if message.voice is not None:
        return {
            "media_type": "voice",
            "file_id": message.voice.file_id,
            "file_name": "voice.ogg",
            "mime_type": message.voice.mime_type or "audio/ogg",
            "file_size": message.voice.file_size or 0,
        }
    if message.audio is not None:
        return {
            "media_type": "audio",
            "file_id": message.audio.file_id,
            "file_name": message.audio.file_name or "audio",
            "mime_type": message.audio.mime_type or "",
            "file_size": message.audio.file_size or 0,
        }
    if message.document is not None and _is_audio_document(message.document):
        return {
            "media_type": "document",
            "file_id": message.document.file_id,
            "file_name": message.document.file_name or "document",
            "mime_type": message.document.mime_type or "",
            "file_size": message.document.file_size or 0,
        }
    return None


async def _download_media(
    bot: Bot, file_id: str, file_name: str
) -> tuple[Path | None, bytes | None]:
    file = await bot.get_file(file_id)
    if not file.file_path:
        return None, None

    file_bytes = await bot.download_file(file.file_path)
    if not file_bytes:
        return None, None

    audio_bytes = file_bytes.read()
    suffix = Path(file_name).suffix or ".bin"
    out_dir = Path("data") / "tmp" / "telegram"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"stt_{uuid4().hex}{suffix}"
    out_path.write_bytes(audio_bytes)
    return out_path, audio_bytes


async def _deliver_tts_reply(
    message: Message,
    reply_text: str | None,
    provider: str,
    audio_bytes: bytes | None,
    error_code: str | None,
    error_message: str | None,
) -> None:
    command_label = _tts_command_label(provider)
    stdout = ""
    stderr = ""
    exit_code: int | None = None
    output_path: Path | None = None
    output_size = 0

    if audio_bytes is not None:
        output_path = _write_tts_audio(audio_bytes, "tutor-reply")
        try:
            output_size = output_path.stat().st_size
        except FileNotFoundError:
            output_size = 0

    _log_tts_diagnostics(
        provider,
        command_label,
        exit_code,
        stdout,
        stderr,
        output_path,
        output_size,
        error_code,
        error_message,
    )

    if not output_path or output_size <= 0:
        logger.warning(
            "TTS output invalid; falling back to text. provider=%s output_path=%s output_size=%s",
            provider,
            str(output_path) if output_path else "",
            output_size,
        )
        fallback_text = "TTS failed: generated audio file is empty."
        if reply_text:
            fallback_text = f"{fallback_text}\n\n{reply_text}"
        await message.answer(fallback_text)
        return

    try:
        voice_file = FSInputFile(output_path)
        await message.answer_voice(voice=voice_file)
    except Exception:
        logger.exception(
            "TTS send voice failed; falling back to text. provider=%s output_path=%s output_size=%s",
            provider,
            str(output_path),
            output_size,
        )
        fallback_text = "TTS failed: unable to send audio."
        if reply_text:
            fallback_text = f"{fallback_text}\n\n{reply_text}"
        await message.answer(fallback_text)


@router.message(lambda m: m.voice is not None or m.audio is not None or m.document is not None)
async def handle_voice(message: Message, bot: Bot) -> None:
    """Handle voice messages."""
    if not message.from_user:
        return

    await message.chat.do(action="typing")

    settings = get_settings()
    stt = build_stt_adapter(settings)
    tts = build_tts_adapter(settings)
    reflection_service = ReflectionVoiceService()
    tutor_service = EnglishTutorService()

    try:
        media = _select_media(message)
        if not media:
            return

        logger.info(
            "Telegram media detected: path=%s media_type=%s file_name=%s mime_type=%s file_size=%s",
            "voice_media" if media["media_type"] == "voice" else "audio_media",
            media["media_type"],
            media["file_name"],
            media["mime_type"],
            media["file_size"],
        )

        out_path, audio_bytes = await _download_media(
            bot, str(media["file_id"]), str(media["file_name"])
        )
        if not out_path or not audio_bytes:
            logger.warning(
                "Failed to download audio media. path=%s media_type=%s file_name=%s mime_type=%s file_size=%s",
                "voice_media" if media["media_type"] == "voice" else "audio_media",
                media["media_type"],
                media["file_name"],
                media["mime_type"],
                media["file_size"],
            )
            await message.answer(
                "Не удалось нормально распознать голосовое. Отправь ещё раз обычным голосовым сообщением."
            )
            return

        logger.info(
            "Audio media ready: path=%s media_type=%s file_name=%s mime_type=%s file_size=%s local_path=%s",
            "voice_media" if media["media_type"] == "voice" else "audio_media",
            media["media_type"],
            media["file_name"],
            media["mime_type"],
            media["file_size"],
            str(out_path),
        )

        active_language = STT_DEFAULT_LANGUAGE
        if get_active_tutor_session(message.from_user.id):
            active_language = STT_TUTOR_LANGUAGE

        reflection_state = get_active_reflection_session(message.from_user.id)
        if reflection_state:
            logger.info(
                "STT request: path=%s language=%s provider=%s",
                "voice_media" if media["media_type"] == "voice" else "audio_media",
                active_language,
                getattr(stt, "__class__", type(stt)).__name__,
            )
            stt_result = await stt.transcribe(audio_bytes, language=active_language)
            logger.info(
                "STT result: status=%s provider=%s language=%s",
                "ok" if stt_result.ok else "error",
                stt_result.provider_ref or "",
                stt_result.language or active_language,
            )
            if not stt_result.ok:
                await message.answer(
                    "Не удалось нормально распознать голосовое. Отправь ещё раз обычным голосовым сообщением."
                )
                return
            transcript = stt_result.text.strip()
            if not transcript:
                await message.answer(
                    "Не удалось нормально распознать голосовое. Отправь ещё раз обычным голосовым сообщением."
                )
                return
            reply_text, error = await reflection_service.handle_user_turn(
                message.from_user.id, transcript
            )
            if error:
                await message.answer(error)
                return
            tts_result = await tts.speak(reply_text or "", voice=settings.tts_voice)
            if tts_result.ok and tts_result.audio_bytes:
                await _deliver_tts_reply(
                    message,
                    reply_text,
                    tts_result.provider_ref or settings.tts_provider or "unknown",
                    tts_result.audio_bytes,
                    tts_result.error_code,
                    tts_result.error_message,
                )
            else:
                _log_tts_diagnostics(
                    tts_result.provider_ref or settings.tts_provider or "unknown",
                    _tts_command_label(tts_result.provider_ref or settings.tts_provider or ""),
                    None,
                    "",
                    "",
                    None,
                    0,
                    tts_result.error_code,
                    tts_result.error_message,
                )
                await message.answer(reply_text or "")
            return

        tutor_state = get_active_tutor_session(message.from_user.id)
        if tutor_state:
            logger.info(
                "STT request: path=%s language=%s provider=%s",
                "voice_media" if media["media_type"] == "voice" else "audio_media",
                active_language,
                getattr(stt, "__class__", type(stt)).__name__,
            )
            stt_result = await stt.transcribe(audio_bytes, language=active_language)
            logger.info(
                "STT result: status=%s provider=%s language=%s",
                "ok" if stt_result.ok else "error",
                stt_result.provider_ref or "",
                stt_result.language or active_language,
            )
            if not stt_result.ok:
                await message.answer(
                    "Не удалось нормально распознать голосовое. Отправь ещё раз обычным голосовым сообщением."
                )
                return
            transcript = stt_result.text.strip()
            if not transcript:
                await message.answer(
                    "Не удалось нормально распознать голосовое. Отправь ещё раз обычным голосовым сообщением."
                )
                return
            reply_text, error = await tutor_service.handle_user_turn(
                message.from_user.id, transcript
            )
            if error:
                await message.answer(error)
                return
            tts_result = await tts.speak(reply_text or "", voice=settings.tts_voice)
            if tts_result.ok and tts_result.audio_bytes:
                await _deliver_tts_reply(
                    message,
                    reply_text,
                    tts_result.provider_ref or settings.tts_provider or "unknown",
                    tts_result.audio_bytes,
                    tts_result.error_code,
                    tts_result.error_message,
                )
            else:
                _log_tts_diagnostics(
                    tts_result.provider_ref or settings.tts_provider or "unknown",
                    _tts_command_label(tts_result.provider_ref or settings.tts_provider or ""),
                    None,
                    "",
                    "",
                    None,
                    0,
                    tts_result.error_code,
                    tts_result.error_message,
                )
                await message.answer(reply_text or "")
            return

        logger.info(
            "STT request: path=%s language=%s provider=%s",
            "voice_media" if media["media_type"] == "voice" else "audio_media",
            active_language,
            getattr(stt, "__class__", type(stt)).__name__,
        )
        stt_result = await stt.transcribe(audio_bytes, language=active_language)
        logger.info(
            "STT result: status=%s provider=%s language=%s",
            "ok" if stt_result.ok else "error",
            stt_result.provider_ref or "",
            stt_result.language or active_language,
        )
        if not stt_result.ok:
            await message.answer(
                "Не удалось нормально распознать голосовое. Отправь ещё раз обычным голосовым сообщением."
            )
            return
        transcript = stt_result.text.strip()
        if not transcript:
            await message.answer(
                "Не удалось нормально распознать голосовое. Отправь ещё раз обычным голосовым сообщением."
            )
            return

        storage = VaultStorage(settings.vault_path)
        timestamp = datetime.fromtimestamp(message.date.timestamp())
        storage.append_to_daily(transcript, timestamp, "[voice]")

        session = SessionStore(settings.vault_path)
        session.append(
            message.from_user.id,
            "voice",
            text=transcript,
            duration=message.voice.duration if message.voice else None,
            msg_id=message.message_id,
        )

        await message.answer(
            f"РЎР‚РЎСџР вЂ№Р’В¤ {transcript}\n\n"
            "Р Р†РЎС™РІР‚Сљ Р В Р Р‹Р В РЎвЂўР РЋРІР‚В¦Р РЋР вЂљР В Р’В°Р В Р вЂ¦Р В Р’ВµР В Р вЂ¦Р В РЎвЂў"
        )
        logger.info("Voice message saved: %d chars", len(transcript))

    except Exception:
        logger.exception("Error processing voice message")
        await message.answer(INTERNAL_ERROR_MESSAGE)
