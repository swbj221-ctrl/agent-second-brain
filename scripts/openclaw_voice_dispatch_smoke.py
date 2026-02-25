"""Smoke checks for transport-agnostic OpenClaw voice dispatch."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from d_brain.integrations.openclaw_bridge import dispatch_command_response, dispatch_voice
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
        self.calls = 0
        self.mime_type = "audio/ogg"

    async def speak(self, text: str, voice: str | None = None) -> TTSResult:
        _ = text, voice
        self.calls += 1
        return TTSResult(audio_bytes=self.audio_bytes, mime_type=self.mime_type, provider_ref="fake-tts")


class FakeAudioTTS(FakeTTS):
    def __init__(self, audio_bytes: bytes, mime_type: str) -> None:
        super().__init__(audio_bytes)
        self.mime_type = mime_type


class FakeTutorService:
    async def handle_user_turn(self, user_id: int, text: str) -> tuple[str | None, str | None]:
        _ = user_id
        return f"Tutor reply: {text}", None


async def _run() -> int:
    failures = 0
    os.environ.setdefault("OPENAI_API_KEY", "voice-smoke-openai-key")
    os.environ.setdefault("MODEL_ROUTE_MAIN_REASONING_PROVIDER", "openai")
    os.environ.setdefault("MODEL_ROUTE_VOICE_REASONING_PROVIDER", "openai")
    os.environ.setdefault("MODEL_ROUTE_ALLOW_OPENAI_TO_LOCAL_FALLBACK", "false")
    os.environ.setdefault("MODEL_ROUTE_FORCE_OPENAI_UNAVAILABLE", "false")

    ru_stt = FakeSTT("privet")
    ru_result = await dispatch_voice(
        user_id=100,
        source_ref="smoke:ru",
        audio_bytes=b"ru-audio",
        media_declared=True,
        mode_hint="default",
        stt=ru_stt,
    )
    ru_ok = ru_stt.last_language == "ru" and ru_result.get("status") == "ok"
    print("case=ru_default")
    print(f"ok={ru_ok}")
    print(f"stt_language={ru_stt.last_language}")
    if not ru_ok:
        failures += 1

    en_stt = FakeSTT("hello")
    en_result = await dispatch_voice(
        user_id=100,
        source_ref="smoke:en",
        audio_bytes=b"en-audio",
        media_declared=True,
        mode_hint="tutor",
        stt=en_stt,
        tts=FakeTTS(b"ogg-bytes"),
        tutor_service=FakeTutorService(),
    )
    en_ok = (
        en_stt.last_language == "en"
        and en_result.get("audio_intent") == "sendVoice"
        and bool(en_result.get("audio_bytes"))
    )
    print("case=en_tutor_mode")
    print(f"ok={en_ok}")
    print(f"stt_language={en_stt.last_language}")
    print(f"audio_intent={en_result.get('audio_intent')}")
    if not en_ok:
        failures += 1

    transcript_only = await dispatch_voice(
        user_id=100,
        source_ref="smoke:transcript-only",
        message_text="Transcript: hello there",
        media_declared=False,
    )
    transcript_diag = transcript_only.get("diagnostics") or {}
    transcript_ok = transcript_only.get("status") == "ok" and bool(
        transcript_diag.get("transcript_only_warning")
    )
    print("case=transcript_only_warning")
    print(f"ok={transcript_ok}")
    print(f"transcript_only_warning={transcript_diag.get('transcript_only_warning', False)}")
    if not transcript_ok:
        failures += 1

    empty_tts = await dispatch_voice(
        user_id=100,
        source_ref="smoke:empty-tts",
        audio_bytes=b"en-audio",
        media_declared=True,
        mode_hint="tutor",
        stt=FakeSTT("hello"),
        tts=FakeTTS(b""),
        tutor_service=FakeTutorService(),
    )
    empty_diag = empty_tts.get("diagnostics") or {}
    empty_ok = (
        empty_tts.get("status") == "ok"
        and empty_tts.get("audio_intent") is None
        and bool(empty_diag.get("tts_empty_output"))
        and "Tutor reply:" in str(empty_tts.get("text") or "")
    )
    print("case=empty_tts_fallback")
    print(f"ok={empty_ok}")
    print(f"audio_intent={empty_tts.get('audio_intent')}")
    print(f"tts_empty_output={empty_diag.get('tts_empty_output', False)}")
    if not empty_ok:
        failures += 1

    dispatch_command_response("/prefs voice off", user_id=201, source_ref="smoke:prefs:voice-off")
    tts_off = FakeTTS(b"ogg-bytes")
    voice_off = await dispatch_voice(
        user_id=201,
        source_ref="smoke:voice-off",
        audio_bytes=b"en-audio",
        media_declared=True,
        mode_hint="tutor",
        stt=FakeSTT("hello"),
        tts=tts_off,
        tutor_service=FakeTutorService(),
    )
    voice_off_diag = voice_off.get("diagnostics") or {}
    voice_off_ok = (
        voice_off.get("status") == "ok"
        and voice_off.get("audio_intent") is None
        and bool(voice_off_diag.get("voice_reply_disabled"))
        and tts_off.calls == 0
    )
    print("case=voice_reply_off_pref")
    print(f"ok={voice_off_ok}")
    print(f"voice_reply_disabled={voice_off_diag.get('voice_reply_disabled', False)}")
    print(f"tts_calls={tts_off.calls}")
    if not voice_off_ok:
        failures += 1

    dispatch_command_response("/prefs lang en_tutor", user_id=202, source_ref="smoke:prefs:lang")
    en_pref_stt = FakeSTT("hello from pref")
    en_pref = await dispatch_voice(
        user_id=202,
        source_ref="smoke:en-pref",
        audio_bytes=b"pref-audio",
        media_declared=True,
        stt=en_pref_stt,
        tts=FakeTTS(b"ogg-bytes"),
        tutor_service=FakeTutorService(),
    )
    en_pref_diag = en_pref.get("diagnostics") or {}
    en_pref_ok = (
        en_pref_stt.last_language == "en"
        and en_pref_diag.get("mode") == "tutor"
        and en_pref.get("status") == "ok"
    )
    print("case=language_mode_en_tutor_pref")
    print(f"ok={en_pref_ok}")
    print(f"stt_language={en_pref_stt.last_language}")
    print(f"mode={en_pref_diag.get('mode')}")
    if not en_pref_ok:
        failures += 1

    dispatch_command_response("/prefs brevity short", user_id=203, source_ref="smoke:prefs:brevity")
    short_warning = await dispatch_voice(
        user_id=203,
        source_ref="smoke:brevity-short",
        message_text="Transcript: hello there",
        media_declared=False,
    )
    short_text = str(short_warning.get("text") or "")
    short_ok = short_warning.get("status") == "ok" and len(short_text) <= 64
    print("case=brevity_short_transcript_warning")
    print(f"ok={short_ok}")
    print(f"text_len={len(short_text)}")
    print(f"text={short_text}")
    if not short_ok:
        failures += 1

    media_priority_stt = FakeSTT("real media transcript")
    media_priority = await dispatch_voice(
        user_id=204,
        source_ref="smoke:media-priority",
        message_text="Transcript: auto transcript should lose",
        audio_bytes=b"real-audio",
        media_declared=True,
        stt=media_priority_stt,
    )
    media_priority_diag = media_priority.get("diagnostics") or {}
    media_priority_ok = (
        media_priority.get("handled") is True
        and media_priority_diag.get("transcript_only_warning") is not True
        and media_priority_diag.get("transcript_len") == len("real media transcript")
    )
    print("case=media_over_transcript_priority")
    print(f"ok={media_priority_ok}")
    print(f"transcript_only_warning={media_priority_diag.get('transcript_only_warning', False)}")
    print(f"transcript_len={media_priority_diag.get('transcript_len')}")
    if not media_priority_ok:
        failures += 1

    send_audio = await dispatch_voice(
        user_id=205,
        source_ref="smoke:send-audio-intent",
        audio_bytes=b"audio",
        media_declared=True,
        mode_hint="tutor",
        stt=FakeSTT("hello"),
        tts=FakeAudioTTS(b"mp3-bytes", "audio/mpeg"),
        tutor_service=FakeTutorService(),
    )
    send_audio_ok = send_audio.get("audio_intent") == "sendAudio" and bool(send_audio.get("audio_bytes"))
    print("case=send_audio_intent_selection")
    print(f"ok={send_audio_ok}")
    print(f"audio_intent={send_audio.get('audio_intent')}")
    if not send_audio_ok:
        failures += 1

    return 0 if failures == 0 else 1


def main() -> int:
    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())
