"""Voice message handler."""

import logging
from pathlib import Path
from uuid import uuid4

from aiogram import Bot, Router
from aiogram.types import FSInputFile, Message

from d_brain.bot.text_utils import safe_answer
from d_brain.config import get_settings
from d_brain.integrations.openclaw_bridge import dispatch_voice

router = Router(name="voice")
logger = logging.getLogger(__name__)
INTERNAL_ERROR_MESSAGE = "Р’СЂРµРјРµРЅРЅР°СЏ РѕС€РёР±РєР°. РџРѕРїСЂРѕР±СѓР№С‚Рµ РїРѕР·Р¶Рµ."
TTS_LOG_TRIM = 500
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
    mime_type: str | None,
    error_code: str | None,
    error_message: str | None,
) -> None:
    logger.info(
        "TTS generation: provider=%s command=%s exit_code=%s stdout=%s stderr=%s "
        "output_path=%s output_size=%s mime_type=%s error_code=%s error_message=%s",
        provider,
        command_label,
        exit_code,
        _trim_log(stdout),
        _trim_log(stderr),
        str(output_path) if output_path else "",
        output_size,
        mime_type or "",
        error_code or "",
        _trim_log(error_message),
    )


def _choose_telegram_method(output_path: Path, mime_type: str | None) -> str:
    suffix = output_path.suffix.lower()
    if suffix in {".ogg", ".opus"}:
        return "sendVoice"
    if mime_type and "ogg" in mime_type.lower():
        return "sendVoice"
    return "sendAudio"


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
    mime_type: str | None = None,
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
        mime_type,
        error_code,
        error_message,
    )

    output_exists = output_path.exists() if output_path else False
    output_size = output_path.stat().st_size if output_path and output_exists else 0
    if not output_path or not output_exists or output_size <= 0:
        logger.warning(
            "TTS output invalid; falling back to text. provider=%s output_path=%s exists=%s output_size=%s",
            provider,
            str(output_path) if output_path else "",
            output_exists,
            output_size,
        )
        fallback_text = "TTS failed: generated audio file is empty."
        if reply_text:
            fallback_text = f"{fallback_text}\n\n{reply_text}"
        await safe_answer(message, fallback_text)
        return

    try:
        method = _choose_telegram_method(output_path, mime_type)
        logger.info(
            "TTS send: method=%s output_path=%s exists=%s output_size=%s",
            method,
            str(output_path),
            output_exists,
            output_size,
        )
        media_file = FSInputFile(output_path)
        if method == "sendVoice":
            await message.answer_voice(voice=media_file)
        else:
            await message.answer_audio(audio=media_file)
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
        await safe_answer(message, fallback_text)


@router.message(lambda m: m.voice is not None or m.audio is not None or m.document is not None)
async def handle_voice(message: Message, bot: Bot) -> None:
    """Handle voice messages."""
    if not message.from_user:
        return

    await message.chat.do(action="typing")
    settings = get_settings()

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
            await safe_answer(message, 
                "Не удалось нормально распознать голосовое. Отправь ещё раз обычным голосовым сообщением."
            )
            return

        response = await dispatch_voice(
            user_id=message.from_user.id,
            source_ref=f"{message.chat.id}:{message.message_id}",
            message_text=message.text or "",
            audio_bytes=audio_bytes,
            media_declared=True,
        )

        diagnostics = response.get("diagnostics") or {}
        output_audio = response.get("audio_bytes")
        if output_audio:
            await _deliver_tts_reply(
                message,
                str(response.get("text") or ""),
                str(diagnostics.get("tts_provider") or settings.tts_provider or "unknown"),
                output_audio if isinstance(output_audio, bytes) else None,
                diagnostics.get("tts_error_code"),
                diagnostics.get("tts_error_message"),
                str(response.get("mime_type") or "audio/ogg"),
            )
            return

        await safe_answer(message, str(response.get("text") or ""))

    except Exception:
        logger.exception("Error processing voice message")
        await safe_answer(message, INTERNAL_ERROR_MESSAGE)

