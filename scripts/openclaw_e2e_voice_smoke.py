"""OpenClaw e2e voice smoke (bridge path, deterministic fakes, no aiogram polling)."""

from __future__ import annotations

import asyncio
import json
import os

from d_brain.integrations.openclaw_bridge import dispatch_voice
from d_brain.services.transcription import STTResult
from d_brain.services.tts import TTSResult


class FakeSTT:
    def __init__(self, text: str) -> None:
        self.text = text
        self.last_language: str | None = None

    async def transcribe(self, audio_bytes: bytes, language: str | None = None) -> STTResult:
        _ = audio_bytes
        self.last_language = language
        return STTResult(text=self.text, language=language, provider_ref="fake-stt")


class FakeTTS:
    def __init__(self, audio_bytes: bytes) -> None:
        self.audio_bytes = audio_bytes

    async def speak(self, text: str, voice: str | None = None) -> TTSResult:
        _ = text, voice
        return TTSResult(audio_bytes=self.audio_bytes, mime_type="audio/ogg", provider_ref="fake-tts")


class FakeTutorService:
    async def handle_user_turn(self, user_id: int, text: str) -> tuple[str | None, str | None]:
        _ = user_id
        return f"Tutor reply: {text}", None


def emit(case: str, response: dict, ok: bool, extra: dict | None = None) -> None:
    payload = {
        "case": case,
        "ok": ok,
        "status": response.get("status"),
        "error_code": response.get("error_code"),
        "text": str(response.get("text") or ""),
        "audio_intent": response.get("audio_intent"),
        "has_audio_bytes": isinstance(response.get("audio_bytes"), bytes),
    }
    diag = response.get("diagnostics") or {}
    payload["diagnostics"] = {
        "stt_language": diag.get("stt_language"),
        "transcript_only_warning": bool(diag.get("transcript_only_warning")),
        "tts_empty_output": bool(diag.get("tts_empty_output")),
    }
    if extra:
        payload.update(extra)
    print(json.dumps(payload, ensure_ascii=True))


async def _run() -> int:
    os.environ.setdefault("OPENAI_API_KEY", "openclaw-e2e-voice-smoke")
    os.environ.setdefault("MODEL_ROUTE_MAIN_REASONING_PROVIDER", "openai")
    os.environ.setdefault("MODEL_ROUTE_VOICE_REASONING_PROVIDER", "openai")
    os.environ.setdefault("MODEL_ROUTE_FORCE_OPENAI_UNAVAILABLE", "false")
    os.environ.setdefault("MODEL_ROUTE_ALLOW_OPENAI_TO_LOCAL_FALLBACK", "false")

    failures = 0

    stt_ru = FakeSTT("привет")
    ru_response = await dispatch_voice(
        user_id=777,
        source_ref="e2e:ru",
        audio_bytes=b"ru-audio",
        media_declared=True,
        mode_hint="default",
        stt=stt_ru,
    )
    ru_ok = ru_response.get("status") == "ok" and stt_ru.last_language == "ru"
    emit("ru_default_stt", ru_response, ru_ok, {"stt_language": stt_ru.last_language})
    if not ru_ok:
        failures += 1

    stt_en = FakeSTT("hello")
    en_response = await dispatch_voice(
        user_id=777,
        source_ref="e2e:en",
        audio_bytes=b"en-audio",
        media_declared=True,
        mode_hint="tutor",
        stt=stt_en,
        tts=FakeTTS(b"ogg-bytes"),
        tutor_service=FakeTutorService(),
    )
    en_ok = (
        en_response.get("status") == "ok"
        and stt_en.last_language == "en"
        and en_response.get("audio_intent") == "sendVoice"
        and isinstance(en_response.get("audio_bytes"), bytes)
    )
    emit("en_tutor_stt_tts", en_response, en_ok, {"stt_language": stt_en.last_language})
    if not en_ok:
        failures += 1

    transcript_response = await dispatch_voice(
        user_id=777,
        source_ref="e2e:transcript-only",
        message_text="Transcript: auto generated text",
        media_declared=False,
    )
    transcript_diag = transcript_response.get("diagnostics") or {}
    transcript_ok = (
        transcript_response.get("status") == "ok"
        and bool(transcript_diag.get("transcript_only_warning"))
    )
    emit("transcript_only_warning", transcript_response, transcript_ok)
    if not transcript_ok:
        failures += 1

    empty_tts_response = await dispatch_voice(
        user_id=777,
        source_ref="e2e:empty-tts",
        audio_bytes=b"en-audio",
        media_declared=True,
        mode_hint="tutor",
        stt=FakeSTT("hello"),
        tts=FakeTTS(b""),
        tutor_service=FakeTutorService(),
    )
    empty_diag = empty_tts_response.get("diagnostics") or {}
    empty_tts_ok = (
        empty_tts_response.get("status") == "ok"
        and empty_tts_response.get("audio_intent") is None
        and bool(empty_diag.get("tts_empty_output"))
        and "Tutor reply:" in str(empty_tts_response.get("text") or "")
    )
    emit("empty_tts_text_fallback", empty_tts_response, empty_tts_ok)
    if not empty_tts_ok:
        failures += 1

    return 0 if failures == 0 else 1


def main() -> int:
    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())
