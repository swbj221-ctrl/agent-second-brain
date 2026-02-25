"""Smoke checks for Telegram voice/media source selection in OpenClaw bridge."""

from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import d_brain.integrations.openclaw_bridge as bridge  # noqa: E402
from d_brain.services.transcription import STTResult  # noqa: E402


class PatchSet:
    def __init__(self) -> None:
        self._items: list[tuple[Any, str, Any]] = []

    def set(self, obj: Any, attr: str, value: Any) -> None:
        self._items.append((obj, attr, getattr(obj, attr)))
        setattr(obj, attr, value)

    def restore(self) -> None:
        for obj, attr, old in reversed(self._items):
            setattr(obj, attr, old)


class _ListHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


class FakeSTT:
    def __init__(self, text: str, *, error_code: str | None = None) -> None:
        self.text = text
        self.error_code = error_code

    async def transcribe(self, audio_bytes: bytes, language: str | None = None) -> STTResult:
        _ = audio_bytes, language
        return STTResult(
            text=self.text,
            language=language,
            provider_ref="fake-stt",
            error_code=self.error_code,
        )


def emit(case: str, ok: bool, **payload: Any) -> None:
    print(json.dumps({"case": case, "ok": bool(ok), **payload}, ensure_ascii=True))


def _contains_file_request(text: str) -> bool:
    lowered = text.lower()
    return ".ogg" in lowered or ".m4a" in lowered or "файл" in lowered


def _find_json_event(messages: list[str], event_name: str) -> dict[str, Any] | None:
    for raw in reversed(messages):
        try:
            data = json.loads(raw)
        except Exception:
            continue
        if data.get("event") == event_name:
            return data
    return None


def _require_evidence_fields(event_obj: dict[str, Any]) -> bool:
    required = [
        "requestId",
        "userIdHash",
        "messageKind",
        "telegramFileIdPresent",
        "telegramFileUniqueIdPresent",
        "downloaderName",
        "downloaderPath",
        "mediaBytesPresent",
        "mediaBytesLen",
        "mediaPathPresent",
        "transcriptLen",
        "transcriptLooksAuto",
        "finalInputSource",
        "finalOutcome",
        "fallbackReason",
        "responseMode",
    ]
    return all(key in event_obj for key in required)


def main() -> int:
    failures = 0
    log_handler = _ListHandler()
    bridge.logger.addHandler(log_handler)
    bridge.logger.setLevel(logging.INFO)
    os.environ.setdefault("TELEGRAM_BOT_TOKEN", "voice-source-smoke-token")
    os.environ.setdefault("OPENAI_API_KEY", "voice-source-smoke-openai")

    with tempfile.TemporaryDirectory(prefix="voice-source-smoke-") as tmp:
        vault_path = Path(tmp) / "vault"
        vault_path.mkdir(parents=True, exist_ok=True)
        os.environ["VAULT_PATH"] = str(vault_path)
        patches = PatchSet()
        try:
            # 1) voice_note_prefers_file_over_transcript
            log_handler.messages.clear()
            downloader_calls: list[tuple[str, str]] = []

            def _voice_downloader(*args: Any, **kwargs: Any) -> bytes:
                file_id = str(kwargs.get("file_id") or args[0])
                media_kind = str(kwargs.get("media_kind") or args[1])
                downloader_calls.append((file_id, media_kind))
                return b"voice-note-bytes"

            patches.set(bridge, "build_stt_adapter", lambda settings=None: FakeSTT("recognized from voice file"))  # noqa: ARG005
            response = bridge.dispatch_voice_from_message(
                {
                    "user_id": 301,
                    "chat_id": 301,
                    "message_id": 1,
                    "text": "Transcript: bad auto transcript",
                    "voice": {
                        "file_id": "voice-file-1",
                        "mime_type": "audio/ogg",
                        "duration": 2,
                    },
                    "telegram_media_downloader": _voice_downloader,
                },
                user_id=301,
                request_id="smoke-v1",
            )
            diag = response.get("diagnostics") or {}
            source_log = _find_json_event(log_handler.messages, "telegram_stt_source_select") or {}
            ok = (
                response.get("status") == "ok"
                and diag.get("stt_source") == "voice_file"
                and diag.get("transcript_only_warning") is not True
                and not _contains_file_request(str(response.get("text") or ""))
                and downloader_calls == [("voice-file-1", "voice")]
                and source_log.get("sttSource") == "voice_file"
                and _require_evidence_fields(source_log)
                and source_log.get("requestId") == "smoke-v1"
                and bool(source_log.get("userIdHash"))
                and source_log.get("messageKind") == "voice"
                and source_log.get("downloaderPath") == "telegram_media_downloader"
            )
            emit(
                "voice_note_prefers_file_over_transcript",
                ok,
                stt_source=diag.get("stt_source"),
                transcript_only_warning=bool(diag.get("transcript_only_warning")),
                downloader_calls=len(downloader_calls),
                source_log_stt_source=source_log.get("sttSource", ""),
            )
            if not ok:
                failures += 1

            # 2) voice_note_download_fail_no_file_request
            log_handler.messages.clear()

            def _fail_downloader(*args: Any, **kwargs: Any) -> bytes:  # pragma: no cover - smoke helper
                raise RuntimeError("download failed")

            response = bridge.dispatch_voice_from_message(
                {
                    "user_id": 302,
                    "chat_id": 302,
                    "message_id": 2,
                    "text": "Transcript: telegram auto transcript",
                    "voice": {
                        "file_id": "voice-file-2",
                        "mime_type": "audio/ogg",
                        "duration": 1,
                    },
                    "telegram_media_downloader": _fail_downloader,
                },
                user_id=302,
                request_id="smoke-v2",
            )
            diag = response.get("diagnostics") or {}
            source_log = _find_json_event(log_handler.messages, "telegram_stt_source_select") or {}
            ok = (
                response.get("status") == "error"
                and diag.get("fallback_reason") == "voice_download_failed"
                and not _contains_file_request(str(response.get("text") or ""))
                and source_log.get("downloadAttempted") is True
                and source_log.get("downloadOk") is False
                and source_log.get("finalInputSource") == "voice_file"
            )
            emit(
                "voice_note_download_fail_no_file_request",
                ok,
                status=response.get("status"),
                fallback_reason=diag.get("fallback_reason"),
                download_attempted=source_log.get("downloadAttempted"),
                download_ok=source_log.get("downloadOk"),
            )
            if not ok:
                failures += 1

            # 3) voice_note_empty_transcript_retry
            log_handler.messages.clear()
            patches.set(bridge, "build_stt_adapter", lambda settings=None: FakeSTT(""))  # noqa: ARG005
            response = bridge.dispatch_voice_from_message(
                {
                    "user_id": 303,
                    "chat_id": 303,
                    "message_id": 3,
                    "voice": {
                        "file_id": "voice-file-3",
                        "mime_type": "audio/ogg",
                        "duration": 2,
                    },
                    "telegram_media_downloader": lambda *args, **kwargs: b"voice-note-empty-stt",  # noqa: ARG005
                },
                user_id=303,
                request_id="smoke-v3",
            )
            diag = response.get("diagnostics") or {}
            reply_text = str(response.get("text") or "")
            ok = (
                response.get("status") == "error"
                and diag.get("fallback_reason") == "empty_transcript_voice_note"
                and ("гром" in reply_text.lower() or "длин" in reply_text.lower() or "повтор" in reply_text.lower())
                and not _contains_file_request(reply_text)
            )
            emit(
                "voice_note_empty_transcript_retry",
                ok,
                fallback_reason=diag.get("fallback_reason"),
                text=reply_text,
            )
            if not ok:
                failures += 1

            # 4) audio_file_path_still_works
            log_handler.messages.clear()
            patches.set(bridge, "build_stt_adapter", lambda settings=None: FakeSTT("recognized from m4a"))  # noqa: ARG005
            response = bridge.dispatch_voice_from_message(
                {
                    "user_id": 304,
                    "chat_id": 304,
                    "message_id": 4,
                    "audio": {
                        "file_id": "audio-file-4",
                        "file_name": "sample.m4a",
                        "mime_type": "audio/mp4",
                    },
                    "telegram_media_downloader": lambda *args, **kwargs: b"m4a-bytes",  # noqa: ARG005
                },
                user_id=304,
                request_id="smoke-v4",
            )
            diag = response.get("diagnostics") or {}
            ok = response.get("status") == "ok" and diag.get("stt_source") == "audio_file"
            emit(
                "audio_file_path_still_works",
                ok,
                status=response.get("status"),
                stt_source=diag.get("stt_source"),
            )
            if not ok:
                failures += 1

            # 5) transcript_only_fallback_when_no_media
            log_handler.messages.clear()
            response = bridge.dispatch_voice_from_message(
                {
                    "user_id": 305,
                    "chat_id": 305,
                    "message_id": 5,
                    "transcript": "Transcript: no media here",
                },
                user_id=305,
                request_id="smoke-v5",
            )
            diag = response.get("diagnostics") or {}
            ok = (
                response.get("status") == "ok"
                and bool(diag.get("transcript_only_warning"))
                and (diag.get("stt_source") in {"transcript", ""})
            )
            emit(
                "transcript_only_fallback_when_no_media",
                ok,
                status=response.get("status"),
                transcript_only_warning=bool(diag.get("transcript_only_warning")),
                stt_source=diag.get("stt_source"),
            )
            if not ok:
                failures += 1

            # 6) nested voice bytes present + transcript present -> bytes win
            log_handler.messages.clear()
            patches.set(bridge, "build_stt_adapter", lambda settings=None: FakeSTT("nested voice bytes"))  # noqa: ARG005
            response = bridge.dispatch_voice_from_message(
                {
                    "user_id": 306,
                    "chat_id": 306,
                    "message_id": 6,
                    "request_id": "smoke-v6",
                    "text": "Transcript: garbage",
                    "voice": {
                        "bytes": b"nested-voice-bytes",
                        "mime_type": "audio/ogg",
                        "duration": 2,
                    },
                },
                user_id=306,
                request_id="smoke-v6",
            )
            diag = response.get("diagnostics") or {}
            select_log = _find_json_event(log_handler.messages, "telegram_stt_source_select") or {}
            ok = (
                response.get("status") == "ok"
                and diag.get("stt_source") == "voice_file"
                and select_log.get("mediaBytesPresent") is True
                and int(select_log.get("mediaBytesLen") or 0) > 0
                and select_log.get("finalInputSource") == "voice_file"
            )
            emit("nested_voice_bytes_with_transcript_prefers_voice_file", ok, stt_source=diag.get("stt_source"))
            if not ok:
                failures += 1

            # 7) malformed voice object + transcript present -> safe transcript fallback
            log_handler.messages.clear()
            response = bridge.dispatch_voice_from_message(
                {
                    "user_id": 307,
                    "chat_id": 307,
                    "message_id": 7,
                    "request_id": "smoke-v7",
                    "text": "Transcript: fallback please",
                    "voice": {
                        "mime_type": "audio/ogg",
                    },
                },
                user_id=307,
                request_id="smoke-v7",
            )
            diag = response.get("diagnostics") or {}
            ingest_log = _find_json_event(log_handler.messages, "telegram_voice_ingest") or {}
            ok = (
                response.get("status") == "ok"
                and bool(diag.get("transcript_only_warning"))
                and not _contains_file_request(str(response.get("text") or ""))
                and ingest_log.get("fallbackReason") in {"transcript_only_auto", "unsupported_media_shape", "transcript_only_no_media"}
                and ingest_log.get("finalOutcome") == "fallback_transcript"
            )
            emit("voice_malformed_shape_safe_transcript_fallback", ok, fallback_reason=ingest_log.get("fallbackReason"))
            if not ok:
                failures += 1

            # 8) downloader exception -> stable fallback + no crash
            log_handler.messages.clear()
            response = bridge.dispatch_voice_from_message(
                {
                    "user_id": 308,
                    "chat_id": 308,
                    "message_id": 8,
                    "request_id": "smoke-v8",
                    "voice": {"file_id": "voice-file-8", "mime_type": "audio/ogg"},
                    "telegram_media_downloader": (lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))),
                },
                user_id=308,
                request_id="smoke-v8",
            )
            diag = response.get("diagnostics") or {}
            ok = response.get("status") == "error" and diag.get("fallback_reason") == "voice_download_failed"
            emit("downloader_exception_stable_fallback", ok, fallback_reason=diag.get("fallback_reason"))
            if not ok:
                failures += 1

            # 9) downloader returns bytes + transcript garbage -> transcript ignored
            log_handler.messages.clear()
            patches.set(bridge, "build_stt_adapter", lambda settings=None: FakeSTT("from downloader bytes"))  # noqa: ARG005
            response = bridge.dispatch_voice_from_message(
                {
                    "user_id": 309,
                    "chat_id": 309,
                    "message_id": 9,
                    "request_id": "smoke-v9",
                    "text": "Transcript: garbage garbage",
                    "voice": {"file_id": "voice-file-9", "mime_type": "audio/ogg"},
                    "media_downloader": lambda *a, **k: b"voice-download-bytes",  # noqa: ARG005
                },
                user_id=309,
                request_id="smoke-v9",
            )
            diag = response.get("diagnostics") or {}
            select_log = _find_json_event(log_handler.messages, "telegram_stt_source_select") or {}
            ok = (
                response.get("status") == "ok"
                and diag.get("stt_source") == "voice_file"
                and select_log.get("downloaderPath") == "media_downloader"
                and select_log.get("finalInputSource") == "voice_file"
            )
            emit("downloader_bytes_overrides_transcript_garbage", ok, stt_source=diag.get("stt_source"))
            if not ok:
                failures += 1

            # 10) document audio/ogg still works
            log_handler.messages.clear()
            patches.set(bridge, "build_stt_adapter", lambda settings=None: FakeSTT("doc ogg ok"))  # noqa: ARG005
            response = bridge.dispatch_voice_from_message(
                {
                    "user_id": 310,
                    "chat_id": 310,
                    "message_id": 10,
                    "request_id": "smoke-v10",
                    "document": {
                        "file_id": "doc-ogg-10",
                        "mime_type": "audio/ogg",
                        "file_name": "voice.ogg",
                    },
                    "download_media": lambda *a, **k: b"doc-ogg-bytes",  # noqa: ARG005
                },
                user_id=310,
                request_id="smoke-v10",
            )
            diag = response.get("diagnostics") or {}
            ok = response.get("status") == "ok" and diag.get("stt_source") == "document_file"
            emit("document_audio_ogg_still_works", ok, stt_source=diag.get("stt_source"))
            if not ok:
                failures += 1
        finally:
            patches.restore()

    bridge.logger.removeHandler(log_handler)
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
