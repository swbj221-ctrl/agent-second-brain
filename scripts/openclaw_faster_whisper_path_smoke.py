"""Focused smoke for faster-whisper live dispatch path and media source lock."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import d_brain.integrations.openclaw_bridge as bridge
from d_brain.integrations.openclaw_bridge import dispatch_voice


class _ListHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


def _find_json_event(messages: list[str], event_name: str, *, stage: str | None = None) -> dict[str, object] | None:
    for raw in reversed(messages):
        try:
            data = json.loads(raw)
        except Exception:
            continue
        if data.get("event") != event_name:
            continue
        if stage is not None and data.get("stage") != stage:
            continue
        return data
    return None


async def _run() -> int:
    failures = 0
    log_handler = _ListHandler()
    bridge.logger.addHandler(log_handler)
    bridge.logger.setLevel(logging.INFO)

    prev_backend = os.environ.get("TELEGRAM_STT_BACKEND")
    prev_mp = os.environ.get("TELEGRAM_STT_MULTIPASS")
    prev_mph = os.environ.get("TELEGRAM_STT_MIXED_HEURISTIC")
    prev_mpl = os.environ.get("TELEGRAM_STT_MULTIPASS_LANGS")
    prev_model = os.environ.get("FASTER_WHISPER_MODEL")
    prev_device = os.environ.get("FASTER_WHISPER_DEVICE")
    prev_compute = os.environ.get("FASTER_WHISPER_COMPUTE_TYPE")
    original_fw = bridge._run_faster_whisper_stt

    os.environ["TELEGRAM_STT_BACKEND"] = "faster_whisper"
    os.environ["TELEGRAM_STT_MULTIPASS"] = "1"
    os.environ["TELEGRAM_STT_MULTIPASS_LANGS"] = "auto,ru,en"
    os.environ["TELEGRAM_STT_MIXED_HEURISTIC"] = "1"
    os.environ["FASTER_WHISPER_MODEL"] = os.environ.get("FASTER_WHISPER_MODEL") or "small"
    os.environ["FASTER_WHISPER_DEVICE"] = os.environ.get("FASTER_WHISPER_DEVICE") or "cpu"
    os.environ["FASTER_WHISPER_COMPUTE_TYPE"] = os.environ.get("FASTER_WHISPER_COMPUTE_TYPE") or "int8"

    async def _fake_fw_stt(
        *,
        audio_path: str | None = None,
        audio_bytes: bytes | None = None,
        pass_lang: str | None = None,
        pass_token: str = "auto",
        diagnostics: dict[str, object] | None = None,
    ) -> tuple[str, str, float | None, list[dict[str, object]], dict[str, object]]:
        _ = audio_path, audio_bytes, diagnostics
        token = str(pass_token or "auto").lower()
        if token == "ru":
            text = "Привет, how are you, ты меня понимаешь?"
            return text, "ru", 0.96, [], {"stt_model": "small", "stt_backend_used": "faster_whisper"}
        if token == "en":
            return "how are you", "en", 0.90, [], {"stt_model": "small", "stt_backend_used": "faster_whisper"}
        return "how are you", pass_lang or "ru", 0.70, [], {"stt_model": "small", "stt_backend_used": "faster_whisper"}

    bridge._run_faster_whisper_stt = _fake_fw_stt  # type: ignore[assignment]
    try:
        result = await dispatch_voice(
            user_id=991,
            source_ref="smoke:fw-source-lock",
            message_text="how are you",
            audio_bytes=b"RIFF\x24\x00\x00\x00WAVEfmt ",
            media_declared=True,
        )
        diag = result.get("diagnostics") or {}
        selected = _find_json_event(log_handler.messages, "telegram_voice_pipeline", stage="stt_multipass_selected") or {}
        text = str(result.get("text") or "")
        ok = (
            result.get("status") == "ok"
            and "Привет" in text
            and "how are you" in text
            and "ты меня понимаешь" in text
            and diag.get("final_transcript_source_used") == "bridge_stt"
            and diag.get("response_text_source") == "bridge_stt"
            and diag.get("outgoing_text_source") == "bridge_stt"
            and diag.get("chat_response_source") == "bridge_stt"
            and selected.get("stage") == "stt_multipass_selected"
        )
        print("case=fw_media_multipass_source_lock")
        print(f"ok={ok}")
        print(f"selected_lang={selected.get('selectedLang')}")
        print(f"text={text[:140]}")
        if not ok:
            failures += 1

        blocked = await dispatch_voice(
            user_id=992,
            source_ref="smoke:fw-media-fail-closed",
            message_text="how are you",
            media_declared=True,
        )
        blocked_diag = blocked.get("diagnostics") or {}
        blocked_ok = (
            blocked.get("status") == "error"
            and blocked_diag.get("final_transcript_source_used") == "none"
            and blocked_diag.get("fallback_reason") == "media_declared_without_bytes"
        )
        print("case=fw_media_turn_blocks_provider_transcript_tail")
        print(f"ok={blocked_ok}")
        print(f"status={blocked.get('status')}")
        print(f"final_source={blocked_diag.get('final_transcript_source_used')}")
        if not blocked_ok:
            failures += 1
    finally:
        bridge._run_faster_whisper_stt = original_fw  # type: ignore[assignment]
        if prev_backend is None:
            os.environ.pop("TELEGRAM_STT_BACKEND", None)
        else:
            os.environ["TELEGRAM_STT_BACKEND"] = prev_backend
        if prev_mp is None:
            os.environ.pop("TELEGRAM_STT_MULTIPASS", None)
        else:
            os.environ["TELEGRAM_STT_MULTIPASS"] = prev_mp
        if prev_mph is None:
            os.environ.pop("TELEGRAM_STT_MIXED_HEURISTIC", None)
        else:
            os.environ["TELEGRAM_STT_MIXED_HEURISTIC"] = prev_mph
        if prev_mpl is None:
            os.environ.pop("TELEGRAM_STT_MULTIPASS_LANGS", None)
        else:
            os.environ["TELEGRAM_STT_MULTIPASS_LANGS"] = prev_mpl
        if prev_model is None:
            os.environ.pop("FASTER_WHISPER_MODEL", None)
        else:
            os.environ["FASTER_WHISPER_MODEL"] = prev_model
        if prev_device is None:
            os.environ.pop("FASTER_WHISPER_DEVICE", None)
        else:
            os.environ["FASTER_WHISPER_DEVICE"] = prev_device
        if prev_compute is None:
            os.environ.pop("FASTER_WHISPER_COMPUTE_TYPE", None)
        else:
            os.environ["FASTER_WHISPER_COMPUTE_TYPE"] = prev_compute
        bridge.logger.removeHandler(log_handler)

    return failures


def main() -> int:
    failures = asyncio.run(_run())
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
