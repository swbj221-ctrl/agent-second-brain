"""Smoke checks for strict Telegram TTS backend policy (local-only by default)."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import d_brain.integrations.openclaw_bridge as bridge


def _restore_env(name: str, previous: str | None) -> None:
    if previous is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = previous


class _TTSProbe:
    def __init__(self) -> None:
        self.calls = 0

    async def speak(self, text: str, *, voice: str = "") -> object:  # pragma: no cover - should not be reached in normal mode
        _ = text, voice
        self.calls += 1
        raise RuntimeError("deepgram_tts_reached")


async def _run() -> int:
    failures = 0
    prev_backend = os.environ.get("TELEGRAM_TTS_BACKEND")
    prev_diag = os.environ.get("OPENCLAW_ALLOW_DEEPGRAM_TTS_DIAGNOSTIC")
    original_piper = bridge._speak_with_piper

    def _piper_ok(*, text: str, detected_language: str = "") -> tuple[str | None, bytes | None, str | None, dict[str, object]]:
        _ = text, detected_language
        return "sendVoice", b"ogg", "audio/ogg", {"tts_backend": "piper", "tts_backend_used": "piper"}

    def _piper_fail(*, text: str, detected_language: str = "") -> tuple[str | None, bytes | None, str | None, dict[str, object]]:
        _ = text, detected_language
        return None, None, None, {
            "tts_backend": "piper",
            "tts_backend_used": "piper",
            "tts_error_code": "piper_failed",
            "tts_error_message": "smoke_forced_piper_failure",
        }

    probe = _TTSProbe()

    try:
        os.environ.pop("OPENCLAW_ALLOW_DEEPGRAM_TTS_DIAGNOSTIC", None)
        os.environ["TELEGRAM_TTS_BACKEND"] = "deepgram"
        resolved = bridge._resolve_tts_backend()
        case_ok = resolved == "piper"
        print("case=tts_deepgram_env_resolves_to_piper")
        print(f"ok={case_ok}")
        print(f"tts_backend={resolved}")
        if not case_ok:
            failures += 1

        bridge._speak_with_piper = _piper_ok  # type: ignore[assignment]
        os.environ["TELEGRAM_TTS_BACKEND"] = "deepgram"
        intent, audio, mime, diag = await bridge._synthesize_reply(
            "hello",
            tts=probe,  # should not be used in normal mode
            tts_voice="",
            detected_language="en",
        )
        case_ok = (
            intent == "sendVoice"
            and bool(audio)
            and mime == "audio/ogg"
            and str(diag.get("tts_backend_used") or "") == "piper"
            and probe.calls == 0
        )
        print("case=tts_normal_mode_no_deepgram_path")
        print(f"ok={case_ok}")
        print(f"tts_backend_used={diag.get('tts_backend_used')}")
        print(f"deepgram_tts_calls={probe.calls}")
        if not case_ok:
            failures += 1

        bridge._speak_with_piper = _piper_fail  # type: ignore[assignment]
        os.environ["TELEGRAM_TTS_BACKEND"] = "auto"
        intent, audio, mime, diag = await bridge._synthesize_reply(
            "hello",
            tts=probe,  # should still not be used without diagnostic override
            tts_voice="",
            detected_language="en",
        )
        case_ok = (
            intent is None
            and audio is None
            and mime is None
            and str(diag.get("tts_backend_used") or "") == "piper"
            and str(diag.get("tts_error_code") or "") in {"piper_failed", "tts_local_failed"}
            and probe.calls == 0
        )
        print("case=tts_local_fail_closed_no_deepgram_fallback")
        print(f"ok={case_ok}")
        print(f"tts_backend_used={diag.get('tts_backend_used')}")
        print(f"tts_error_code={diag.get('tts_error_code')}")
        print(f"deepgram_tts_calls={probe.calls}")
        if not case_ok:
            failures += 1

    finally:
        bridge._speak_with_piper = original_piper  # type: ignore[assignment]
        _restore_env("TELEGRAM_TTS_BACKEND", prev_backend)
        _restore_env("OPENCLAW_ALLOW_DEEPGRAM_TTS_DIAGNOSTIC", prev_diag)

    return failures


def main() -> int:
    failures = asyncio.run(_run())
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

