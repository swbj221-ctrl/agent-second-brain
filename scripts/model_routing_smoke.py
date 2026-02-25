"""Smoke checks for strict model routing policy (no aiogram)."""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import sys
from pathlib import Path


def ensure_src_on_path() -> None:
    root = Path(__file__).resolve().parents[1]
    src = root / "src"
    if src.exists() and str(src) not in sys.path:
        sys.path.insert(0, str(src))


ensure_src_on_path()

from d_brain.config import get_settings  # noqa: E402
from d_brain.integrations.openclaw_bridge import dispatch_command, dispatch_voice  # noqa: E402
from d_brain.services.model_routing import (  # noqa: E402
    TASK_COMMAND_STATUS,
    TASK_CRON_SUMMARY,
    TASK_HEARTBEAT,
    resolve_route,
)
from d_brain.services.transcription import STTResult  # noqa: E402
from d_brain.services.tts import TTSResult  # noqa: E402
from d_brain.sidecar.dispatcher import handle_request  # noqa: E402


class FakeSTT:
    async def transcribe(self, audio_bytes: bytes, language: str | None = None) -> STTResult:
        _ = audio_bytes
        return STTResult(text="hello routing", language=language, provider_ref="fake-stt")


class FakeTTS:
    async def speak(self, text: str, voice: str | None = None) -> TTSResult:
        _ = text, voice
        return TTSResult(audio_bytes=b"ogg-bytes", mime_type="audio/ogg", provider_ref="fake-tts")


class FakeTutorService:
    async def handle_user_turn(self, user_id: int, text: str) -> tuple[str | None, str | None]:
        _ = user_id
        return f"Tutor reply: {text}", None


def _set_env(**kwargs: str) -> None:
    for key, value in kwargs.items():
        os.environ[key] = value


def _sidecar_request(action: str, payload: dict) -> dict:
    return handle_request(
        {
            "request_id": f"routing-smoke-{action}",
            "user_id": "routing-smoke",
            "action": action,
            "payload": payload,
            "metadata": {"source": "routing-smoke"},
        }
    )


async def _run() -> int:
    failures = 0
    _set_env(
        OPENAI_API_KEY="smoke-openai-key",
        MODEL_ROUTE_FORCE_OPENAI_UNAVAILABLE="false",
        MODEL_ROUTE_FORCE_LOCAL_UNAVAILABLE="false",
        MODEL_ROUTE_ALLOW_LOCAL_TO_OPENAI_FALLBACK="true",
        MODEL_ROUTE_ALLOW_OPENAI_TO_LOCAL_FALLBACK="false",
        MODEL_ROUTE_COMMAND_STATUS_PROVIDER="deterministic",
        MODEL_ROUTE_MAIN_REASONING_PROVIDER="openai",
        MODEL_ROUTE_VOICE_REASONING_PROVIDER="openai",
        MODEL_ROUTE_HEARTBEAT_PROVIDER="local",
        MODEL_ROUTE_CRON_SUMMARY_PROVIDER="local",
    )

    status_output = dispatch_command("/status", user_id=123, source_ref="smoke:status")
    status_route = resolve_route(TASK_COMMAND_STATUS, get_settings())
    status_ok = bool(status_output) and status_route.selected_provider in {"deterministic", "openai"}
    print("case=status_command_policy")
    print(f"ok={status_ok}")
    print(f"provider={status_route.selected_provider}")
    print(f"model={status_route.selected_model}")
    if not status_ok:
        failures += 1

    voice_response = await dispatch_voice(
        user_id=123,
        source_ref="smoke:voice",
        audio_bytes=b"voice-audio",
        media_declared=True,
        mode_hint="tutor",
        stt=FakeSTT(),
        tts=FakeTTS(),
        tutor_service=FakeTutorService(),
    )
    voice_route = ((voice_response.get("diagnostics") or {}).get("reasoning_route") or {})
    voice_ok = voice_response.get("status") == "ok" and voice_route.get("provider") == "openai"
    print("case=voice_reasoning_policy")
    print(f"ok={voice_ok}")
    print(f"provider={voice_route.get('provider', '')}")
    print(f"fallback_used={voice_route.get('fallback_used', False)}")
    if not voice_ok:
        failures += 1

    heartbeat_response = _sidecar_request(
        "heartbeat_tick",
        {"event_source": "smoke", "event_details": {"purpose": "routing"}},
    )
    heartbeat_route = (
        ((heartbeat_response.get("data") or {}).get("event_details") or {}).get("model_routing")
        or resolve_route(TASK_HEARTBEAT, get_settings()).to_diagnostics()
    )
    heartbeat_ok = heartbeat_response.get("status") == "ok" and heartbeat_route.get("provider") == "local"
    print("case=heartbeat_policy")
    print(f"ok={heartbeat_ok}")
    print(f"provider={heartbeat_route.get('provider', '')}")
    if not heartbeat_ok:
        failures += 1

    digest_response = _sidecar_request("digest_generate", {"digest_type": "system_state"})
    digest_route = (digest_response.get("data") or {}).get("model_routing") or {}
    digest_ok = digest_response.get("status") == "ok" and digest_route.get("provider") == "local"
    print("case=cron_summary_policy")
    print(f"ok={digest_ok}")
    print(f"provider={digest_route.get('provider', '')}")
    if not digest_ok:
        failures += 1

    _set_env(MODEL_ROUTE_FORCE_LOCAL_UNAVAILABLE="true")
    fallback_route = resolve_route(TASK_HEARTBEAT, get_settings())
    fallback_ok = (
        fallback_route.allowed
        and fallback_route.selected_provider == "openai"
        and fallback_route.fallback_used
    )
    print("case=local_fallback_to_openai")
    print(f"ok={fallback_ok}")
    print(f"provider={fallback_route.selected_provider}")
    print(f"fallback_used={fallback_route.fallback_used}")
    print(f"reason={fallback_route.reason or ''}")
    if not fallback_ok:
        failures += 1

    _set_env(
        MODEL_ROUTE_FORCE_LOCAL_UNAVAILABLE="false",
        MODEL_ROUTE_FORCE_OPENAI_UNAVAILABLE="true",
        MODEL_ROUTE_ALLOW_OPENAI_TO_LOCAL_FALLBACK="false",
    )
    openai_down_response = await dispatch_voice(
        user_id=123,
        source_ref="smoke:voice-openai-down",
        audio_bytes=b"voice-audio",
        media_declared=True,
        mode_hint="tutor",
        stt=FakeSTT(),
        tts=FakeTTS(),
        tutor_service=FakeTutorService(),
    )
    openai_down_route = ((openai_down_response.get("diagnostics") or {}).get("reasoning_route") or {})
    openai_down_ok = (
        openai_down_response.get("status") == "error"
        and openai_down_response.get("error_code") == "reasoning_provider_unavailable"
        and openai_down_route.get("provider") == "openai"
    )
    print("case=openai_unavailable_main_reasoning")
    print(f"ok={openai_down_ok}")
    print(f"status={openai_down_response.get('status')}")
    print(f"error_code={openai_down_response.get('error_code')}")
    print(f"provider={openai_down_route.get('provider', '')}")
    if not openai_down_ok:
        failures += 1

    settings = get_settings()
    with sqlite3.connect(settings.db_path) as conn:
        heartbeat_count = conn.execute("SELECT COUNT(*) FROM heartbeat_logs;").fetchone()[0]
        digest_count = conn.execute("SELECT COUNT(*) FROM digests;").fetchone()[0]
    print("case=db_rows")
    print(json.dumps({"heartbeat_logs": heartbeat_count, "digests": digest_count}))

    return 0 if failures == 0 else 1


def main() -> int:
    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())
