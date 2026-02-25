"""Fallback stability smoke for OpenClaw-first routing (JSONL)."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import logging
import os
import sys
import tempfile
from pathlib import Path
from typing import Any


def ensure_paths() -> Path:
    root = Path(__file__).resolve().parents[1]
    src = root / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    return root


def load_adapter(root: Path):
    adapter_path = root / "vault" / ".claude" / "skills" / "openclaw-main" / "adapter.py"
    spec = importlib.util.spec_from_file_location("openclaw_main_adapter_fallback_smoke", adapter_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load adapter: {adapter_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def emit(case: str, ok: bool, **payload: Any) -> None:
    out = {"case": case, "ok": bool(ok), **payload}
    print(json.dumps(out, ensure_ascii=True))


class PatchSet:
    def __init__(self) -> None:
        self._items: list[tuple[Any, str, Any]] = []

    def set(self, obj: Any, attr: str, value: Any) -> None:
        self._items.append((obj, attr, getattr(obj, attr)))
        setattr(obj, attr, value)

    def restore(self) -> None:
        for obj, attr, old in reversed(self._items):
            setattr(obj, attr, old)


class FakeRoute:
    def __init__(self) -> None:
        self.task_type = "voice"
        self.selected_provider = "openai"
        self.selected_model = "smoke"
        self.fallback_used = False
        self.allowed = True
        self.reason = ""


class FakeTTSResult:
    def __init__(self, audio_bytes: bytes | None) -> None:
        self.audio_bytes = audio_bytes
        self.mime_type = "audio/ogg"
        self.provider_ref = "fake-tts"
        self.error_code = None
        self.error_message = None

    @property
    def ok(self) -> bool:
        return True


class FakeEmptyTTS:
    async def speak(self, text: str, voice: str | None = None) -> FakeTTSResult:
        _ = text, voice
        return FakeTTSResult(b"")


class FakeGoodTTS:
    async def speak(self, text: str, voice: str | None = None) -> FakeTTSResult:
        _ = text, voice
        return FakeTTSResult(b"\x4f\x67\x67\x53-non-empty")


class FakeTimeoutSTT:
    async def transcribe(self, audio_bytes: bytes, language: str | None = None):  # noqa: ARG002
        raise asyncio.TimeoutError()


class FakeReflectionService:
    async def handle_user_turn(self, user_id: int, text: str) -> tuple[str | None, str | None]:  # noqa: ARG002
        return f"Reflection reply: {text}", None


class _ListHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


def main() -> int:
    root = ensure_paths()
    adapter = load_adapter(root)
    import d_brain.integrations.openclaw_bridge as bridge  # noqa: WPS433

    failures = 0
    log_handler = _ListHandler()
    adapter.logger.addHandler(log_handler)
    adapter.logger.setLevel(logging.INFO)
    with tempfile.TemporaryDirectory(prefix="openclaw-fallback-smoke-") as tmp:
        vault_dir = Path(tmp) / "vault"
        vault_dir.mkdir(parents=True, exist_ok=True)
        os.environ["VAULT_PATH"] = str(vault_dir)
        os.environ["TELEGRAM_BOT_TOKEN"] = "fallback-smoke-token"
        os.environ["OPENAI_API_KEY"] = "fallback-smoke-openai"

        # stt_timeout_nonfatal
        patches = PatchSet()
        try:
            patches.set(bridge, "resolve_route", lambda *args, **kwargs: FakeRoute())  # noqa: ARG005
            patches.set(bridge, "build_stt_adapter", lambda settings=None: FakeTimeoutSTT())  # noqa: ARG005
            patches.set(bridge, "build_tts_adapter", lambda settings=None: FakeEmptyTTS())  # noqa: ARG005
            patches.set(bridge, "ReflectionVoiceService", lambda: FakeReflectionService())
            patches.set(bridge, "get_active_reflection_session", lambda user_id: None)  # noqa: ARG005
            response = adapter.main_handler_response(
                {
                    "user_id": 123,
                    "chat_id": 123,
                    "message_id": 1,
                    "mode": "reflection",
                    "audio_bytes": b"voice",
                    "has_media": True,
                }
            )
            ok = bool(response.get("handled")) and response.get("route") == "voice" and response.get("status") == "error"
            ok = ok and str((response.get("diagnostics") or {}).get("stt_error_code") or "") in {"stt_timeout", ""}
            emit(
                "stt_timeout_nonfatal",
                ok,
                route=response.get("route"),
                status=response.get("status"),
                error_code=response.get("diagnostics", {}).get("stt_error_code") or response.get("error_code"),
                fallback_reason=(response.get("meta") or {}).get("fallback_reason"),
            )
            if not ok:
                failures += 1
        except Exception as exc:
            emit("stt_timeout_nonfatal", False, error=f"{exc.__class__.__name__}:{exc}")
            failures += 1
        finally:
            patches.restore()

        # tts_empty_nonfatal
        patches = PatchSet()
        try:
            log_handler.messages.clear()
            class FakeSTTResult:
                ok = True
                provider_ref = "fake-stt"
                error_code = None
                error_message = None
                text = "privet"

            class FakeSTT:
                async def transcribe(self, audio_bytes: bytes, language: str | None = None):  # noqa: ARG002
                    return FakeSTTResult()

            patches.set(bridge, "resolve_route", lambda *args, **kwargs: FakeRoute())  # noqa: ARG005
            patches.set(bridge, "build_stt_adapter", lambda settings=None: FakeSTT())  # noqa: ARG005
            patches.set(bridge, "build_tts_adapter", lambda settings=None: FakeEmptyTTS())  # noqa: ARG005
            patches.set(bridge, "ReflectionVoiceService", lambda: FakeReflectionService())
            patches.set(bridge, "get_active_reflection_session", lambda user_id: None)  # noqa: ARG005
            response = adapter.main_handler_response(
                {
                    "user_id": 123,
                    "chat_id": 123,
                    "message_id": 2,
                    "mode": "reflection",
                    "audio_bytes": b"voice",
                    "has_media": True,
                }
            )
            diagnostics = response.get("diagnostics") or {}
            guard_logged = any(
                '"event":"openclaw_adapter_media_guard"' in msg and '"reason":"empty_tts_output"' in msg
                for msg in log_handler.messages
            )
            ok = bool(response.get("handled")) and response.get("status") == "ok"
            ok = ok and response.get("audio_intent") is None and bool(diagnostics.get("tts_empty_output"))
            emit(
                "tts_empty_nonfatal",
                ok,
                route=response.get("route"),
                status=response.get("status"),
                audio_intent=response.get("audio_intent"),
                tts_empty_output=bool(diagnostics.get("tts_empty_output")),
                guard_logged=guard_logged,
                no_media_send_inferred=response.get("audio_intent") is None,
                fallback_reason=(response.get("meta") or {}).get("fallback_reason"),
            )
            if not ok:
                failures += 1
        except Exception as exc:
            emit("tts_empty_nonfatal", False, error=f"{exc.__class__.__name__}:{exc}")
            failures += 1
        finally:
            patches.restore()

        # adapter_empty_tts_output_guard (zero-size file path)
        try:
            log_handler.messages.clear()
            empty_path = Path(tmp) / "empty_tts.ogg"
            empty_path.write_bytes(b"")
            response = adapter._build_adapter_response(  # type: ignore[attr-defined]
                text="Fallback text",
                handled=True,
                route="voice",
                bridge_handled=True,
                status="ok",
                user_id=123,
                chat_id=123,
                media_detected=True,
                audio_intent="sendVoice",
                audio_path=str(empty_path),
                audio_bytes=None,
                mime_type="audio/ogg",
                diagnostics={"tts_provider": "edge"},
                source_ref="smoke:empty-file",
                handler="bridge",
                latency_ms=1,
                request_id="smoke-empty-guard",
            )
            diagnostics = response.get("diagnostics") or {}
            guard_logged = any(
                '"event":"openclaw_adapter_media_guard"' in msg and '"reason":"empty_tts_output"' in msg
                for msg in log_handler.messages
            )
            ok = response.get("audio_intent") is None and bool(diagnostics.get("tts_empty_output"))
            ok = ok and (response.get("meta") or {}).get("fallback_reason") == "empty_tts_output"
            ok = ok and guard_logged
            emit(
                "adapter_empty_tts_output_guard",
                ok,
                audio_intent=response.get("audio_intent"),
                fallback_reason=(response.get("meta") or {}).get("fallback_reason"),
                tts_empty_output=bool(diagnostics.get("tts_empty_output")),
                guard_logged=guard_logged,
            )
            if not ok:
                failures += 1
        except Exception as exc:
            emit("adapter_empty_tts_output_guard", False, error=f"{exc.__class__.__name__}:{exc}")
            failures += 1

        # tts_valid_nonempty_media_path
        patches = PatchSet()
        try:
            log_handler.messages.clear()

            class FakeSTTResult:
                ok = True
                provider_ref = "fake-stt"
                error_code = None
                error_message = None
                text = "privet"

            class FakeSTT:
                async def transcribe(self, audio_bytes: bytes, language: str | None = None):  # noqa: ARG002
                    return FakeSTTResult()

            patches.set(bridge, "resolve_route", lambda *args, **kwargs: FakeRoute())  # noqa: ARG005
            patches.set(bridge, "build_stt_adapter", lambda settings=None: FakeSTT())  # noqa: ARG005
            patches.set(bridge, "build_tts_adapter", lambda settings=None: FakeGoodTTS())  # noqa: ARG005
            patches.set(bridge, "ReflectionVoiceService", lambda: FakeReflectionService())
            patches.set(bridge, "get_active_reflection_session", lambda user_id: None)  # noqa: ARG005
            response = adapter.main_handler_response(
                {
                    "user_id": 123,
                    "chat_id": 123,
                    "message_id": 22,
                    "mode": "reflection",
                    "audio_bytes": b"voice",
                    "has_media": True,
                }
            )
            guard_logged = any('"event":"openclaw_adapter_media_guard"' in msg for msg in log_handler.messages)
            ok = bool(response.get("handled")) and response.get("status") == "ok"
            ok = ok and response.get("audio_intent") in {"sendVoice", "sendAudio"}
            ok = ok and not bool((response.get("meta") or {}).get("fallback_reason"))
            ok = ok and not guard_logged
            emit(
                "tts_valid_nonempty_media_path",
                ok,
                route=response.get("route"),
                status=response.get("status"),
                audio_intent=response.get("audio_intent"),
                guard_logged=guard_logged,
                fallback_reason=(response.get("meta") or {}).get("fallback_reason"),
            )
            if not ok:
                failures += 1
        except Exception as exc:
            emit("tts_valid_nonempty_media_path", False, error=f"{exc.__class__.__name__}:{exc}")
            failures += 1
        finally:
            patches.restore()

        # ingestion_exception_nonfatal
        patches = PatchSet()
        try:
            patches.set(bridge, "ingest_message_event", lambda payload: (_ for _ in ()).throw(RuntimeError("boom")))  # noqa: ARG005
            response = adapter.main_handler_response(
                {
                    "user_id": 123,
                    "chat_id": 123,
                    "message_id": 3,
                    "text": "/help",
                }
            )
            ok = bool(response.get("handled")) and response.get("route") == "command" and bool(response.get("text"))
            emit(
                "ingestion_exception_nonfatal",
                ok,
                route=response.get("route"),
                status=response.get("status"),
                fallback_reason=(response.get("meta") or {}).get("fallback_reason"),
            )
            if not ok:
                failures += 1
        except Exception as exc:
            emit("ingestion_exception_nonfatal", False, error=f"{exc.__class__.__name__}:{exc}")
            failures += 1
        finally:
            patches.restore()

    adapter.logger.removeHandler(log_handler)
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
