"""Short OpenClaw-first stabilization matrix (offline, no aiogram polling)."""

from __future__ import annotations

import asyncio
import json
import os
import re

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

    async def speak(self, text: str, voice: str | None = None) -> TTSResult:
        _ = text, voice
        return TTSResult(audio_bytes=self.audio_bytes, mime_type="audio/ogg", provider_ref="fake-tts")


class FakeTutorService:
    async def handle_user_turn(self, user_id: int, text: str) -> tuple[str | None, str | None]:
        _ = user_id
        return f"Tutor reply: {text}", None


def _emit(**row: object) -> None:
    print(json.dumps(row, ensure_ascii=True))


def _extract_plan_id(text: str) -> int | None:
    match = re.search(r"#(?P<id>\d+)", text or "")
    return int(match.group("id")) if match else None


async def _run() -> int:
    os.environ.setdefault("OPENAI_API_KEY", "stabilization-smoke-openai-key")
    os.environ.setdefault("MODEL_ROUTE_MAIN_REASONING_PROVIDER", "openai")
    os.environ.setdefault("MODEL_ROUTE_VOICE_REASONING_PROVIDER", "openai")
    failures = 0
    user_id = 123

    plan_id: int | None = None
    command_cases = [
        "/help",
        "/status",
        "/plan add Тест E2E",
        "/plan list",
    ]
    for idx, cmd in enumerate(command_cases, start=1):
        out = dispatch_command_response(cmd, user_id=user_id, source_ref=f"e2e:cmd:{idx}")
        text = str(out.get("text") or "")
        if cmd.startswith("/plan add "):
            plan_id = _extract_plan_id(text)
        ok = bool(out.get("ok"))
        _emit(
            input=cmd,
            bridge_path="command",
            result_type="text",
            ok=ok,
            error_code=out.get("error_code"),
            text=text,
        )
        if not ok:
            failures += 1

    if plan_id is not None:
        for cmd in (f"/plan done {plan_id}", f"/plan delete {plan_id}"):
            out = dispatch_command_response(cmd, user_id=user_id, source_ref="e2e:cmd:plan-mutate")
            ok = bool(out.get("ok"))
            _emit(
                input=cmd,
                bridge_path="command",
                result_type="text",
                ok=ok,
                error_code=out.get("error_code"),
                text=str(out.get("text") or ""),
            )
            if not ok:
                failures += 1
    else:
        failures += 1
        _emit(input="/plan add Тест E2E", bridge_path="command", result_type="text", ok=False, error="plan_id_not_extracted")

    plain_text = await dispatch_voice(
        user_id=user_id,
        source_ref="e2e:text-default",
        message_text="просто текст без команды",
        media_declared=False,
    )
    _emit(
        input="plain_text_non_command",
        bridge_path="text",
        result_type="text" if plain_text.get("handled") else "ignored",
        ok=bool(plain_text.get("handled")) if plain_text.get("handled") else True,
        error_code=plain_text.get("error_code"),
        text=str(plain_text.get("text") or ""),
        handled=bool(plain_text.get("handled")),
    )

    ru_stt = FakeSTT("привет")
    ru_voice = await dispatch_voice(
        user_id=user_id,
        source_ref="e2e:voice-ru",
        audio_bytes=b"ru-audio",
        media_declared=True,
        mode_hint="default",
        stt=ru_stt,
    )
    ru_audio = bool(ru_voice.get("audio_intent"))
    _emit(
        input="voice_ru_media",
        bridge_path="voice",
        result_type="audio" if ru_audio else "text",
        ok=str(ru_voice.get("status") or "ok") == "ok",
        error_code=ru_voice.get("error_code"),
        audio_intent=ru_voice.get("audio_intent"),
        fallback=bool((ru_voice.get("diagnostics") or {}).get("tts_empty_output")),
    )

    en_stt = FakeSTT("hello")
    tutor_voice = await dispatch_voice(
        user_id=user_id,
        source_ref="e2e:voice-tutor",
        audio_bytes=b"en-audio",
        media_declared=True,
        mode_hint="tutor",
        stt=en_stt,
        tts=FakeTTS(b"ogg-bytes"),
        tutor_service=FakeTutorService(),
    )
    tutor_ok = str(tutor_voice.get("status") or "ok") == "ok" and tutor_voice.get("audio_intent") == "sendVoice"
    _emit(
        input="voice_tutor_mode",
        bridge_path="voice",
        result_type="audio",
        ok=tutor_ok,
        error_code=tutor_voice.get("error_code"),
        audio_intent=tutor_voice.get("audio_intent"),
        stt_language=en_stt.last_language,
    )
    if not tutor_ok:
        failures += 1

    tts_fallback = await dispatch_voice(
        user_id=user_id,
        source_ref="e2e:tts-fallback",
        audio_bytes=b"en-audio",
        media_declared=True,
        mode_hint="tutor",
        stt=FakeSTT("ответь голосом"),
        tts=FakeTTS(b""),
        tutor_service=FakeTutorService(),
    )
    diag = tts_fallback.get("diagnostics") or {}
    fallback_ok = (
        str(tts_fallback.get("status") or "ok") == "ok"
        and tts_fallback.get("audio_intent") is None
        and bool(diag.get("tts_empty_output"))
    )
    _emit(
        input="voice_tts_fallback_request",
        bridge_path="voice",
        result_type="text_fallback",
        ok=fallback_ok,
        error_code=tts_fallback.get("error_code"),
        audio_intent=tts_fallback.get("audio_intent"),
        fallback_reason="tts_empty_output" if diag.get("tts_empty_output") else "",
    )
    if not fallback_ok:
        failures += 1

    return 1 if failures else 0


def main() -> int:
    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())

