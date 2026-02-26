"""Smoke checks for strict Telegram STT backend policy (faster-whisper only)."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import tempfile
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


def _has_deepgram_stt_markers(messages: list[str]) -> bool:
    needles = (
        '"sttBackend":"deepgram"',
        '"sttBackendUsed":"deepgram"',
        '"sttProvider":"deepgram"',
        '"provider_ref":"deepgram"',
    )
    return any(any(needle in raw for needle in needles) for raw in messages)


def _restore_env(name: str, previous: str | None) -> None:
    if previous is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = previous


async def _run() -> int:
    failures = 0
    log_handler = _ListHandler()
    bridge.logger.addHandler(log_handler)
    bridge.logger.setLevel(logging.INFO)

    original_fw = bridge._run_faster_whisper_stt
    prev_backend = os.environ.get("TELEGRAM_STT_BACKEND")
    prev_mp = os.environ.get("TELEGRAM_STT_MULTIPASS")
    prev_mph = os.environ.get("TELEGRAM_STT_MIXED_HEURISTIC")
    prev_mpl = os.environ.get("TELEGRAM_STT_MULTIPASS_LANGS")
    prev_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    prev_openai = os.environ.get("OPENAI_API_KEY")
    prev_vault = os.environ.get("VAULT_PATH")

    os.environ["TELEGRAM_BOT_TOKEN"] = os.environ.get("TELEGRAM_BOT_TOKEN") or "stt-policy-smoke-token"
    os.environ["OPENAI_API_KEY"] = os.environ.get("OPENAI_API_KEY") or "stt-policy-openai-key"
    os.environ["TELEGRAM_STT_MULTIPASS"] = "0"
    os.environ.pop("TELEGRAM_STT_MIXED_HEURISTIC", None)
    os.environ.pop("TELEGRAM_STT_MULTIPASS_LANGS", None)

    vault_path = Path(tempfile.mkdtemp(prefix="stt-backend-policy-smoke-")) / "vault"
    vault_path.mkdir(parents=True, exist_ok=True)
    os.environ["VAULT_PATH"] = str(vault_path)

    async def _fw_ok(
        *,
        audio_path: str | None = None,
        audio_bytes: bytes | None = None,
        pass_lang: str | None = None,
        pass_token: str = "auto",
        diagnostics: dict[str, object] | None = None,
    ) -> tuple[str, str, float | None, list[dict[str, object]], dict[str, object]]:
        _ = audio_path, audio_bytes, pass_lang, pass_token, diagnostics
        return "Привет, how are you, ты меня понимаешь?", "ru", 0.98, [], {"stt_model": "small"}

    async def _fw_fail(
        *,
        audio_path: str | None = None,
        audio_bytes: bytes | None = None,
        pass_lang: str | None = None,
        pass_token: str = "auto",
        diagnostics: dict[str, object] | None = None,
    ) -> tuple[str, str, float | None, list[dict[str, object]], dict[str, object]]:
        _ = audio_path, audio_bytes, pass_lang, pass_token, diagnostics
        return "", "ru", None, [], {
            "error_code": "faster_whisper_import_failed",
            "error_message": "smoke_forced_failure",
            "stt_model": "small",
        }

    try:
        bridge._run_faster_whisper_stt = _fw_ok  # type: ignore[assignment]

        # case: explicit faster_whisper backend.
        log_handler.messages.clear()
        os.environ["TELEGRAM_STT_BACKEND"] = "faster_whisper"
        fw_result = await dispatch_voice(
            user_id=301,
            source_ref="smoke:fw-only",
            message_text="how are you",
            audio_bytes=b"RIFF\x24\x00\x00\x00WAVEfmt ",
            media_declared=True,
        )
        fw_diag = fw_result.get("diagnostics") or {}
        fw_start = _find_json_event(log_handler.messages, "telegram_voice_pipeline", stage="stt_request_start") or {}
        fw_ok = (
            fw_result.get("status") == "ok"
            and fw_diag.get("stt_backend") == "faster_whisper"
            and fw_diag.get("stt_backend_used") == "faster_whisper"
            and fw_diag.get("final_transcript_source_used") == "bridge_stt"
            and fw_start.get("sttBackend") == "faster_whisper"
            and fw_start.get("sttProvider") == "faster_whisper"
            and not _has_deepgram_stt_markers(log_handler.messages)
        )
        print("case=fw_backend_selected")
        print(f"ok={fw_ok}")
        print(f"stt_backend={fw_diag.get('stt_backend')}")
        print(f"stt_backend_used={fw_diag.get('stt_backend_used')}")
        if not fw_ok:
            failures += 1

        # case: deepgram env must still resolve to faster_whisper in runtime path.
        log_handler.messages.clear()
        os.environ["TELEGRAM_STT_BACKEND"] = "deepgram"
        deepgram_env_result = await dispatch_voice(
            user_id=302,
            source_ref="smoke:deepgram-env-ignored",
            message_text="how are you",
            audio_bytes=b"RIFF\x24\x00\x00\x00WAVEfmt ",
            media_declared=True,
        )
        deepgram_env_diag = deepgram_env_result.get("diagnostics") or {}
        deepgram_env_start = _find_json_event(log_handler.messages, "telegram_voice_pipeline", stage="stt_request_start") or {}
        deepgram_env_ok = (
            deepgram_env_result.get("status") == "ok"
            and deepgram_env_diag.get("stt_backend") == "faster_whisper"
            and deepgram_env_diag.get("stt_backend_used") == "faster_whisper"
            and deepgram_env_start.get("sttBackend") == "faster_whisper"
            and deepgram_env_start.get("sttProvider") == "faster_whisper"
            and not _has_deepgram_stt_markers(log_handler.messages)
        )
        print("case=deepgram_env_not_selected")
        print(f"ok={deepgram_env_ok}")
        print(f"stt_backend={deepgram_env_diag.get('stt_backend')}")
        print(f"stt_backend_used={deepgram_env_diag.get('stt_backend_used')}")
        if not deepgram_env_ok:
            failures += 1

        # case: faster-whisper unavailable must fail-closed without deepgram fallback.
        log_handler.messages.clear()
        bridge._run_faster_whisper_stt = _fw_fail  # type: ignore[assignment]
        os.environ["TELEGRAM_STT_BACKEND"] = "deepgram"
        fw_fail_result = await dispatch_voice(
            user_id=303,
            source_ref="smoke:fw-fail-closed",
            message_text="how are you",
            audio_bytes=b"RIFF\x24\x00\x00\x00WAVEfmt ",
            media_declared=True,
        )
        fw_fail_diag = fw_fail_result.get("diagnostics") or {}
        fw_fail_ok = (
            fw_fail_result.get("status") == "error"
            and fw_fail_diag.get("stt_backend") == "faster_whisper"
            and fw_fail_diag.get("stt_backend_used") == "faster_whisper"
            and fw_fail_diag.get("final_transcript_source_used") == "none"
            and fw_fail_diag.get("fallback_reason") == "stt_error"
            and fw_fail_result.get("error_code") == "faster_whisper_import_failed"
            and not _has_deepgram_stt_markers(log_handler.messages)
        )
        print("case=fw_unavailable_fail_closed_no_deepgram_fallback")
        print(f"ok={fw_fail_ok}")
        print(f"status={fw_fail_result.get('status')}")
        print(f"error_code={fw_fail_result.get('error_code')}")
        print(f"fallback_reason={fw_fail_diag.get('fallback_reason')}")
        if not fw_fail_ok:
            failures += 1
    finally:
        bridge._run_faster_whisper_stt = original_fw  # type: ignore[assignment]
        bridge.logger.removeHandler(log_handler)
        _restore_env("TELEGRAM_STT_BACKEND", prev_backend)
        _restore_env("TELEGRAM_STT_MULTIPASS", prev_mp)
        _restore_env("TELEGRAM_STT_MIXED_HEURISTIC", prev_mph)
        _restore_env("TELEGRAM_STT_MULTIPASS_LANGS", prev_mpl)
        _restore_env("TELEGRAM_BOT_TOKEN", prev_token)
        _restore_env("OPENAI_API_KEY", prev_openai)
        _restore_env("VAULT_PATH", prev_vault)

    return failures


def main() -> int:
    failures = asyncio.run(_run())
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

