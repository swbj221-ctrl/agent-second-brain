"""OpenClaw command bridge (no aiogram dependency)."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
import hashlib
import json
import logging
import re
import subprocess
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any, TypedDict
from uuid import uuid4

from d_brain.bot.text_utils import fix_mojibake
from d_brain.config import get_settings
from d_brain import __version__ as D_BRAIN_VERSION
from d_brain.integrations.openclaw_outbound import build_openclaw_outbound
from d_brain.integrations.health import get_health_snapshot
from d_brain.memory.ingestion import ingest_message_event
from d_brain.integrations.heartbeat_runner import (
    HEARTBEAT_INTERVAL_MAX,
    HEARTBEAT_INTERVAL_MIN,
    JOB_DIGEST_DAILY,
    JOB_HEARTBEAT_TICK,
    build_job_specs,
    get_digest_status,
    get_digest_target,
    get_scheduler_config,
    get_heartbeat_status,
    run_digest_daily_sync,
    set_digest_target,
    set_digest_target_enabled,
    clear_digest_target,
    set_digest_enabled,
    set_digest_time,
    set_heartbeat_enabled,
    set_heartbeat_interval,
)
from d_brain.integrations.openclaw_scheduler_adapter import build_scheduler_adapter
from d_brain.services.english_tutor import EnglishTutorService, get_active_tutor_session
from d_brain.services.model_routing import (
    TASK_COMMAND_STATUS,
    TASK_LIGHT_CLASSIFICATION,
    TASK_MAIN_REASONING,
    TASK_VOICE_REPLY_REASONING,
    resolve_route,
)
from d_brain.services.reflection_voice import (
    ReflectionVoiceService,
    get_active_reflection_session,
)
from d_brain.services.session import SessionStore
from d_brain.services.sidecar_client import call_sidecar_action
from d_brain.services.storage import VaultStorage
from d_brain.services.transcription import STTAdapter, STT_TIMEOUT_S, build_stt_adapter
from d_brain.services.tts import TTSAdapter, TTSResult, TTS_TIMEOUT_S, build_tts_adapter
from d_brain.ux_actions import build_help_text, build_status_text

logger = logging.getLogger(__name__)
BRIDGE_STT_TIMEOUT_S = max(float(STT_TIMEOUT_S), 1.0) + 2.0
BRIDGE_TTS_TIMEOUT_S = max(float(TTS_TIMEOUT_S), 1.0) + 2.0
BRIDGE_GIT_TIMEOUT_S = 1.5
BRIDGE_DIAG_SIDECAR_PROBE_TIMEOUT_S = 1.5
USAGE_HB = (
    "\u0418\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u043d\u0438\u0435: "
    "/hb now | /hb status | /hb interval <minutes> | /hb on | /hb off"
)
USAGE_DIGEST = (
    "\u0418\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u043d\u0438\u0435: "
    "/digest now | /digest preview | /digest status | /digest on | /digest off | /digest time HH:MM"
)
USAGE_DIGEST_TARGET = (
    "\u0418\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u043d\u0438\u0435: /digest target here|show|on|off|clear|test\n"
    "\u041f\u0440\u0438\u043c\u0435\u0440: /digest target here"
)
USAGE_CRON = "\u0418\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u043d\u0438\u0435: /cron list | /cron run <job> | /cron sync"
COMMAND_ROUTE_UNAVAILABLE_RU = (
    "\u041c\u0430\u0440\u0448\u0440\u0443\u0442 \u043a\u043e\u043c\u0430\u043d\u0434\u044b "
    "\u0441\u0435\u0439\u0447\u0430\u0441 \u043d\u0435\u0434\u043e\u0441\u0442\u0443\u043f\u0435\u043d. "
    "\u041f\u043e\u043f\u0440\u043e\u0431\u0443\u0439\u0442\u0435 \u043f\u043e\u0437\u0436\u0435."
)
NOT_CONFIGURED_RU = "\u041d\u0435 \u043d\u0430\u0441\u0442\u0440\u043e\u0435\u043d\u043e"
PLAN_LIST_MAX_DISPLAY = 20
USAGE_PLAN_DONE = "Использование: /plan done <id>"
USAGE_PLAN_DELETE = "Использование: /plan delete <id>"
USAGE_VOICE = "Использование: /voice on | /voice off | /voice status"
USAGE_PREFS = (
    "Использование: /prefs | /prefs brevity short|normal | "
    "/prefs lang ru|en_tutor | /prefs voice on|off"
)
DUPLICATE_GUARD_TTL_S = 30.0
SIDECAR_CALL_TIMEOUT_S = 3.0
MAX_COMMAND_TEXT_CHARS = 2048

_DUPLICATE_CACHE_LOCK = threading.Lock()
_DUPLICATE_CACHE: dict[str, tuple[float, Any]] = {}
_VALID_LANGUAGE_MODES = {"ru", "en_tutor"}
_VALID_BREVITY = {"short", "normal"}
_PROCESS_START_UTC = datetime.utcnow()
_PROCESS_START_MONOTONIC = time.monotonic()
_GIT_COMMIT_CACHE: str | None = None
_OBS_LOCK = threading.Lock()
_OBS_COUNTERS: dict[str, int] = {}
_OBS_LAST_ERROR_AT: str | None = None
_OBS_RECENT_ERRORS: deque[dict[str, str]] = deque(maxlen=20)

_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s,;]+"),
    re.compile(r"(?i)\b(openai_api_key|deepgram_api_key|telegram_bot_token|api[_-]?key|token|secret)\b\s*[:=]\s*([^\s,;]+)"),
    re.compile(r"\bsk-[A-Za-z0-9_\-]{12,}\b"),
)

_VOICE_FALLBACK_REASON_WHITELIST = {
    "voice_download_not_attempted",
    "voice_download_failed",
    "media_declared_without_bytes",
    "stt_error",
    "stt_empty",
    "empty_transcript_voice_note",
    "transcript_only_auto",
    "transcript_only_no_media",
    "no_voice_content",
    "unsupported_media_shape",
}


def _utc_now_z() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _sanitize_text_for_logs(value: Any, *, max_len: int = 240) -> str:
    text = str(value or "")
    for pattern in _SECRET_PATTERNS:
        if pattern.pattern.startswith("(?i)(authorization"):
            text = pattern.sub(r"\1[redacted]", text)
        elif "openai_api_key" in pattern.pattern:
            text = pattern.sub(lambda m: f"{m.group(1)}=[redacted]", text)
        else:
            text = pattern.sub("[redacted]", text)
    text = " ".join(text.split())
    return text[:max_len]


def _hash_user_id_for_logs(user_id: Any) -> str:
    raw = str(user_id or "").strip()
    if not raw:
        return ""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def _safe_log_basename(path_value: Any) -> str:
    path_text = str(path_value or "").strip()
    if not path_text:
        return ""
    try:
        return Path(path_text).name[:120]
    except Exception:  # pragma: no cover - defensive
        return path_text.split("/")[-1].split("\\")[-1][:120]


def _normalize_voice_fallback_reason(value: Any) -> str:
    reason = str(value or "").strip()
    if not reason:
        return ""
    if reason in _VOICE_FALLBACK_REASON_WHITELIST:
        return reason
    lowered = reason.lower()
    if lowered in {"voice_stt_failed", "stt_failed", "stt_timeout"}:
        return "stt_error"
    if lowered.startswith("downloader_"):
        return "voice_download_failed"
    if lowered.startswith("audio_download_") or lowered.startswith("document_download_"):
        return "stt_error"
    if lowered.startswith("media_path_"):
        return "stt_error"
    if lowered in {"transcript_only", "transcript_fallback"}:
        return "transcript_only_no_media"
    return "stt_error"


def _voice_message_kind_from_flags(payload: dict[str, Any]) -> str:
    if bool(payload.get("hasVoice")):
        return "voice"
    if bool(payload.get("hasAudio")):
        return "audio"
    if bool(payload.get("hasDocument")):
        return "document"
    return "transcript_only"


def _safe_downloader_name(value: Any) -> str:
    if not callable(value):
        return ""
    name = getattr(value, "__name__", "") or getattr(value, "__qualname__", "") or value.__class__.__name__
    return _sanitize_text_for_logs(name, max_len=80)


def _voice_response_mode_from_payload(payload: dict[str, Any]) -> str:
    response_mode = str(payload.get("responseMode") or payload.get("response_mode") or "").strip()
    if response_mode in {"text", "voice", "audio"}:
        return response_mode
    audio_intent = str(payload.get("audioIntent") or payload.get("audio_intent") or "").strip()
    if audio_intent == "sendVoice":
        return "voice"
    if audio_intent == "sendAudio":
        return "audio"
    return "text" if bool(payload.get("handled")) or bool(payload.get("status")) else ""


def _voice_final_outcome_from_payload(payload: dict[str, Any]) -> str:
    explicit = str(payload.get("finalOutcome") or payload.get("final_outcome") or "").strip()
    if explicit:
        return explicit
    fallback_reason = _normalize_voice_fallback_reason(payload.get("fallbackReason") or payload.get("fallback_reason"))
    stt_attempted = bool(payload.get("sttAttempted") or payload.get("stt_attempted"))
    stt_ok = bool(payload.get("sttOk") or payload.get("stt_ok"))
    final_input_source = str(payload.get("finalInputSource") or payload.get("final_input_source") or payload.get("sttSource") or payload.get("stt_source") or "").strip()
    if stt_attempted and stt_ok:
        return "stt_ok"
    if stt_attempted and fallback_reason in {"stt_empty", "empty_transcript_voice_note"}:
        return "stt_empty"
    if stt_attempted and not stt_ok:
        return "stt_error"
    if final_input_source == "transcript" and fallback_reason in {"transcript_only_auto", "transcript_only_no_media", "unsupported_media_shape"}:
        return "fallback_transcript"
    if fallback_reason in {"no_voice_content", "media_declared_without_bytes"}:
        return "fallback_no_media"
    return ""


def _obs_counter_key(handler: str, error_type: str) -> str:
    return f"{handler}|{error_type}"


def _obs_record_error(*, handler: str, error_type: str, source: str = "", user_id: int | None = None) -> None:
    global _OBS_LAST_ERROR_AT
    when = _utc_now_z()
    with _OBS_LOCK:
        key = _obs_counter_key(handler, error_type)
        _OBS_COUNTERS[key] = int(_OBS_COUNTERS.get(key, 0)) + 1
        _OBS_LAST_ERROR_AT = when
        _OBS_RECENT_ERRORS.append(
            {
                "ts": when,
                "handler": str(handler)[:80],
                "error_type": str(error_type)[:80],
                "source": str(source or "")[:120],
                "user_id": str(user_id or "")[:40],
            }
        )


def get_runtime_observability_snapshot() -> dict[str, Any]:
    with _OBS_LOCK:
        counters = dict(_OBS_COUNTERS)
        last_error_at = _OBS_LAST_ERROR_AT
        recent = list(_OBS_RECENT_ERRORS)
    grouped: dict[str, int] = {}
    for key, count in counters.items():
        _, _, error_type = key.partition("|")
        grouped[error_type] = grouped.get(error_type, 0) + int(count)
    return {
        "process_start_utc": _PROCESS_START_UTC.replace(microsecond=0).isoformat() + "Z",
        "uptime_s": int(max(time.monotonic() - _PROCESS_START_MONOTONIC, 0)),
        "error_counters": counters,
        "error_counts_by_type": grouped,
        "last_error_at": last_error_at,
        "recent_errors": recent[-5:],
    }


def _record_runtime_error_for_test(handler: str, error_type: str, source: str = "test") -> None:
    _obs_record_error(handler=handler, error_type=error_type, source=source, user_id=0)


def _obs_increment_counter(name: str) -> None:
    if not name:
        return
    with _OBS_LOCK:
        _OBS_COUNTERS[name] = int(_OBS_COUNTERS.get(name, 0)) + 1



class OpenClawBridgeResponse(TypedDict, total=False):
    text: str | None
    audio_intent: str | None
    audio_path: str | None
    meta: dict[str, Any]
    ok: bool
    error_code: str
    # Legacy compatibility fields (still used by adapter/tests)
    handled: bool
    status: str
    audio_bytes: bytes | None
    mime_type: str | None
    diagnostics: dict[str, Any]


def _build_bridge_response(
    *,
    ok: bool,
    text: str | None = None,
    audio_intent: str | None = None,
    audio_path: str | None = None,
    meta: dict[str, Any] | None = None,
    error_code: str | None = None,
    handled: bool | None = None,
    status: str | None = None,
    audio_bytes: bytes | None = None,
    mime_type: str | None = None,
    diagnostics: dict[str, Any] | None = None,
) -> OpenClawBridgeResponse:
    payload: OpenClawBridgeResponse = {
        "text": text,
        "audio_intent": audio_intent,
        "audio_path": audio_path,
        "meta": meta or {},
        "ok": bool(ok),
    }
    if error_code:
        payload["error_code"] = str(error_code)
    if handled is not None:
        payload["handled"] = bool(handled)
    if status is not None:
        payload["status"] = str(status)
    if audio_bytes is not None:
        payload["audio_bytes"] = audio_bytes
    if mime_type is not None:
        payload["mime_type"] = mime_type
    if diagnostics is not None:
        payload["diagnostics"] = diagnostics
    return payload


def normalize_bridge_response(value: str | None | dict[str, Any]) -> OpenClawBridgeResponse:
    if isinstance(value, dict):
        text = value.get("text")
        status = str(value.get("status") or "ok")
        handled = bool(value.get("handled", True))
        diagnostics = value.get("diagnostics") if isinstance(value.get("diagnostics"), dict) else {}
        ok = bool(value.get("ok", handled and status == "ok"))
        return _build_bridge_response(
            ok=ok,
            text=str(text) if text is not None else None,
            audio_intent=str(value.get("audio_intent")) if value.get("audio_intent") else None,
            audio_path=str(value.get("audio_path")) if value.get("audio_path") else None,
            meta=dict(value.get("meta") or {}),
            error_code=str(value.get("error_code")) if value.get("error_code") else None,
            handled=handled,
            status=status,
            audio_bytes=value.get("audio_bytes") if isinstance(value.get("audio_bytes"), bytes) else None,
            mime_type=str(value.get("mime_type")) if value.get("mime_type") else None,
            diagnostics=diagnostics,
        )
    return _build_bridge_response(
        ok=bool(value is not None),
        text=str(value) if value is not None else None,
        meta={"route": "command", "normalized": True},
        handled=bool(value is not None),
        status="ok" if value is not None else "ignored",
        diagnostics={},
    )

def _format_error(code: str | None, message: str | None) -> str:
    if code == "not_found":
        return fix_mojibake("Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р В Р вЂ№Р В Р Р‹Р РЋРІвЂћСћР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р Р†Р вЂљРІвЂћСћР В РІР‚в„ўР вЂ™Р’ВµР В Р’В Р вЂ™Р’В Р В Р’В Р В РІР‚в„–Р В Р’В Р В РІР‚В Р В Р’В Р Р†Р вЂљРЎв„ўР В Р Р‹Р Р†РІР‚С›РЎС› Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р Р†Р вЂљРІвЂћСћР В РІР‚в„ўР вЂ™Р’В·Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р Р†Р вЂљРІвЂћСћР В РІР‚в„ўР вЂ™Р’В°Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р Р†Р вЂљРЎСљР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р вЂ™Р’ВР В Р’В Р вЂ™Р’В Р В Р’В Р В РІР‚в„–Р В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРЎС™Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р Р†Р вЂљРІвЂћСћР В РІР‚в„ўР вЂ™Р’ВµР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р В РІР‚В Р В Р вЂ Р В РІР‚С™Р РЋРІР‚С”Р В Р вЂ Р В РІР‚С™Р Р†Р вЂљРЎС™.")
    if code == "invalid_payload":
        return fix_mojibake("Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р В Р вЂ№Р В Р Р‹Р РЋРІвЂћСћР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р Р†Р вЂљРІвЂћСћР В РІР‚в„ўР вЂ™Р’ВµР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р РЋРЎС™Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р РЋРЎвЂєР В Р’В Р вЂ™Р’В Р В Р’В Р В РІР‚в„–Р В Р’В Р вЂ™Р’В Р В Р вЂ Р В РІР‚С™Р РЋРІвЂћСћР В Р’В Р вЂ™Р’В Р В Р’В Р В РІР‚в„–Р В Р’В Р вЂ™Р’В Р В Р вЂ Р В РІР‚С™Р РЋРІвЂћСћР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р Р†Р вЂљРІвЂћСћР В РІР‚в„ўР вЂ™Р’ВµР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р РЋРЎС™Р В Р’В Р вЂ™Р’В Р В Р’В Р В РІР‚в„–Р В Р’В Р В РІР‚В Р В Р’В Р Р†Р вЂљРЎв„ўР В Р Р‹Р Р†РІР‚С›РЎС›Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р вЂ™Р’В Р В Р вЂ Р В РІР‚С™Р вЂ™Р’В¦Р В Р’В Р вЂ™Р’В Р В Р’В Р В РІР‚в„–Р В Р’В Р В РІР‚В Р В Р’В Р Р†Р вЂљРЎв„ўР В Р вЂ Р Р†Р вЂљРЎвЂєР Р†Р вЂљРІР‚СљР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р В РІР‚В Р В Р вЂ Р В РІР‚С™Р РЋРІР‚С”Р В Р вЂ Р В РІР‚С™Р Р†Р вЂљРЎС™ Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р вЂ™Р’В Р В Р вЂ Р В РІР‚С™Р вЂ™Р’В Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р вЂ™Р’В Р В Р вЂ Р В РІР‚С™Р вЂ™Р’В Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р РЋРЎвЂєР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р РЋРЎвЂєР В Р вЂ Р В РІР‚С™Р вЂ™Р’В. Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р Р†Р вЂљРІвЂћСћР В РІР‚в„ўР вЂ™Р’ВР В Р’В Р вЂ™Р’В Р В Р’В Р В РІР‚в„–Р В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРЎС™Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р Р†Р вЂљРЎСљР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р РЋРЎвЂєР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р Р†Р вЂљРІвЂћСћР В РІР‚в„ўР вЂ™Р’В»Р В Р’В Р вЂ™Р’В Р В Р’В Р В РІР‚в„–Р В Р’В Р вЂ™Р’В Р В Р’В Р Р†Р вЂљР’В°Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р Р†Р вЂљРІвЂћСћР В РІР‚в„ўР вЂ™Р’В·Р В Р’В Р вЂ™Р’В Р В Р’В Р В РІР‚в„–Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р РЋРЎв„ўР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р В РІР‚В Р В Р вЂ Р В РІР‚С™Р РЋРІР‚С”Р В Р вЂ Р В РІР‚С™Р Р†Р вЂљРЎС™ /help Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р РЋРЎвЂєР В Р вЂ Р В РІР‚С™Р вЂ™Р’ВР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р Р†Р вЂљРІвЂћСћР В РІР‚в„ўР вЂ™Р’В»Р В Р’В Р вЂ™Р’В Р В Р’В Р В РІР‚в„–Р В Р’В Р вЂ™Р’В Р В Р’В Р В Р РЏ Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р Р†Р вЂљРЎСљР В Р’В Р вЂ™Р’В Р В Р’В Р В РІР‚в„–Р В Р’В Р вЂ™Р’В Р В Р вЂ Р В РІР‚С™Р РЋРІвЂћСћР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р вЂ™Р’ВР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р В Р вЂ№Р В РІР‚в„ўР вЂ™Р’ВР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р Р†Р вЂљРІвЂћСћР В РІР‚в„ўР вЂ™Р’ВµР В Р’В Р вЂ™Р’В Р В Р’В Р В РІР‚в„–Р В Р’В Р вЂ™Р’В Р В Р вЂ Р В РІР‚С™Р РЋРІвЂћСћР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р РЋРЎвЂєР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р вЂ™Р’В Р В Р вЂ Р В РІР‚С™Р вЂ™Р’В ")
    if code == "payload_too_large":
        return fix_mojibake("Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р вЂ™Р’В Р В Р’В Р Р†Р вЂљРІвЂћвЂ“Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р РЋРЎвЂєР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р РЋРЎвЂєР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р Р†Р вЂљРІвЂћСћР В РІР‚в„ўР вЂ™Р’В±Р В Р’В Р вЂ™Р’В Р В Р’В Р В РІР‚в„–Р В Р’В Р В РІР‚В Р В Р’В Р Р†Р вЂљРЎв„ўР В РІР‚в„ўР вЂ™Р’В°Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р Р†Р вЂљРІвЂћСћР В РІР‚в„ўР вЂ™Р’ВµР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р вЂ™Р’В Р В Р вЂ Р В РІР‚С™Р вЂ™Р’В¦Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р вЂ™Р’ВР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р Р†Р вЂљРІвЂћСћР В РІР‚в„ўР вЂ™Р’Вµ Р В Р’В Р вЂ™Р’В Р В Р’В Р В РІР‚в„–Р В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРЎС™Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р Р†Р вЂљРІвЂћСћР В РІР‚в„ўР вЂ™Р’В»Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р вЂ™Р’ВР В Р’В Р вЂ™Р’В Р В Р’В Р В РІР‚в„–Р В Р’В Р В РІР‚В Р В Р вЂ Р В РІР‚С™Р РЋРІвЂћСћР В РІР‚в„ўР вЂ™Р’В¬Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р РЋРЎС™Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р РЋРЎвЂєР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р В Р вЂ№Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р РЋРЎвЂєР В Р вЂ Р В РІР‚С™Р вЂ™Р’ВР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р Р†Р вЂљРІвЂћСћР В РІР‚в„ўР вЂ™Р’В»Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р вЂ™Р’ВР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р вЂ™Р’В Р В Р вЂ Р В РІР‚С™Р вЂ™Р’В¦Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р вЂ™Р’В Р В Р вЂ Р В РІР‚С™Р вЂ™Р’В¦Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р РЋРЎвЂєР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р Р†Р вЂљРІвЂћСћР В РІР‚в„ўР вЂ™Р’Вµ")
    if code in {"storage_error", "summary_error", "internal_error"}:
        return fix_mojibake("Р В Р’В Р вЂ™Р’В Р В Р’В Р Р†Р вЂљР’В Р В Р’В Р В Р вЂ№Р В Р Р‹Р РЋРІвЂћСћР В Р’В Р В РІР‚В Р В Р’В Р Р†Р вЂљРЎв„ўР В Р Р‹Р РЋРІвЂћСћ Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р В Р вЂ№Р В Р Р‹Р РЋРІвЂћСћР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р Р†Р вЂљРІвЂћСћР В РІР‚в„ўР вЂ™Р’Вµ Р В Р’В Р вЂ™Р’В Р В Р’В Р В РІР‚в„–Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р РЋРЎв„ўР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р РЋРЎвЂєР В Р вЂ Р В РІР‚С™Р вЂ™Р’ВР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р Р†Р вЂљРІвЂћСћР В РІР‚в„ўР вЂ™Р’В°Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р Р†Р вЂљРІвЂћСћР В РІР‚в„ўР вЂ™Р’В»Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р РЋРЎвЂєР В Р’В Р вЂ™Р’В Р В Р’В Р В РІР‚в„–Р В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРЎС™Р В Р’В Р вЂ™Р’В Р В Р’В Р В РІР‚в„–Р В Р’В Р вЂ™Р’В Р В Р’В Р Р†Р вЂљР’В° Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р вЂ™Р’В Р В Р вЂ Р В РІР‚С™Р вЂ™Р’В Р В Р’В Р вЂ™Р’В Р В Р’В Р В РІР‚в„–Р В Р’В Р В РІР‚В Р В Р’В Р Р†Р вЂљРЎв„ўР В Р вЂ Р Р†Р вЂљРЎвЂєР Р†Р вЂљРІР‚СљР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р Р†Р вЂљРЎСљР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р РЋРЎвЂєР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р Р†Р вЂљРІвЂћСћР В РІР‚в„ўР вЂ™Р’В»Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р вЂ™Р’В Р В Р вЂ Р В РІР‚С™Р вЂ™Р’В¦Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р вЂ™Р’ВР В Р’В Р вЂ™Р’В Р В Р’В Р В РІР‚в„–Р В Р’В Р В РІР‚В Р В Р’В Р Р†Р вЂљРЎв„ўР В Р Р‹Р Р†РІР‚С›РЎС›Р В Р’В Р вЂ™Р’В Р В Р’В Р В РІР‚в„–Р В Р’В Р вЂ™Р’В Р В Р’В Р Р†Р вЂљР’В° Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р РЋРЎС™Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р РЋРЎвЂєР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р В Р вЂ№Р В РІР‚в„ўР вЂ™Р’ВР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р Р†Р вЂљРІвЂћСћР В РІР‚в„ўР вЂ™Р’В°Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р вЂ™Р’В Р В Р вЂ Р В РІР‚С™Р вЂ™Р’В¦Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р РЋРЎвЂєР В Р вЂ Р В РІР‚С™Р вЂ™Р’ВР В Р’В Р вЂ™Р’В Р В Р’В Р В РІР‚в„–Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р РЋРЎв„ў. Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р В Р вЂ№Р В Р Р‹Р РЋРЎСџР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р РЋРЎвЂєР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р Р†Р вЂљРЎСљР В Р’В Р вЂ™Р’В Р В Р’В Р В РІР‚в„–Р В Р’В Р вЂ™Р’В Р В Р вЂ Р В РІР‚С™Р РЋРІвЂћСћР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р РЋРЎвЂєР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р Р†Р вЂљРІвЂћСћР В РІР‚в„ўР вЂ™Р’В±Р В Р’В Р вЂ™Р’В Р В Р’В Р В РІР‚в„–Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р РЋРЎв„ўР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р В РІР‚В Р В Р вЂ Р В РІР‚С™Р РЋРІР‚С”Р В Р вЂ Р В РІР‚С™Р Р†Р вЂљРЎС™ Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р Р†Р вЂљРІвЂћСћР В РІР‚в„ўР вЂ™Р’ВµР В Р’В Р вЂ™Р’В Р В Р’В Р В РІР‚в„–Р В Р’В Р В РІР‚В Р В Р’В Р Р†Р вЂљРЎв„ўР В РІР‚в„ўР вЂ™Р’В°Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р Р†Р вЂљРІвЂћСћР В РІР‚в„ўР вЂ™Р’Вµ Р В Р’В Р вЂ™Р’В Р В Р’В Р В РІР‚в„–Р В Р’В Р вЂ™Р’В Р В Р вЂ Р В РІР‚С™Р РЋРІвЂћСћР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р Р†Р вЂљРІвЂћСћР В РІР‚в„ўР вЂ™Р’В°Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р Р†Р вЂљРІвЂћСћР В РІР‚в„ўР вЂ™Р’В· Р В Р’В Р вЂ™Р’В Р В Р’В Р В РІР‚в„–Р В Р’В Р В РІР‚В Р В Р’В Р Р†Р вЂљРЎв„ўР В Р’В Р В РІР‚в„–Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р Р†Р вЂљРІвЂћСћР В РІР‚в„ўР вЂ™Р’ВµР В Р’В Р вЂ™Р’В Р В Р’В Р В РІР‚в„–Р В Р’В Р вЂ™Р’В Р В Р вЂ Р В РІР‚С™Р РЋРІвЂћСћР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р Р†Р вЂљРІвЂћСћР В РІР‚в„ўР вЂ™Р’ВµР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р Р†Р вЂљРІвЂћСћР В РІР‚в„ўР вЂ™Р’В· Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р В Р вЂ№Р В РІР‚в„ўР вЂ™Р’ВР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р вЂ™Р’ВР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р вЂ™Р’В Р В Р вЂ Р В РІР‚С™Р вЂ™Р’В¦Р В Р’В Р вЂ™Р’В Р В Р’В Р В РІР‚в„–Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р РЋРЎв„ўР В Р’В Р вЂ™Р’В Р В Р’В Р В РІР‚в„–Р В Р’В Р В РІР‚В Р В Р’В Р Р†Р вЂљРЎв„ўР В Р Р‹Р Р†РІР‚С›РЎС›Р В Р’В Р вЂ™Р’В Р В Р’В Р В РІР‚в„–Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р РЋРЎв„ў.")
    return fix_mojibake("Р В Р’В Р вЂ™Р’В Р В Р’В Р Р†Р вЂљР’В Р В Р’В Р В Р вЂ№Р В Р Р‹Р РЋРІвЂћСћР В Р’В Р В РІР‚В Р В Р’В Р Р†Р вЂљРЎв„ўР В Р Р‹Р РЋРІвЂћСћ Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р В Р вЂ№Р В Р Р‹Р РЋРІвЂћСћР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р Р†Р вЂљРІвЂћСћР В РІР‚в„ўР вЂ™Р’Вµ Р В Р’В Р вЂ™Р’В Р В Р’В Р В РІР‚в„–Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р РЋРЎв„ўР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р РЋРЎвЂєР В Р вЂ Р В РІР‚С™Р вЂ™Р’ВР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р Р†Р вЂљРІвЂћСћР В РІР‚в„ўР вЂ™Р’В°Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р Р†Р вЂљРІвЂћСћР В РІР‚в„ўР вЂ™Р’В»Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р РЋРЎвЂєР В Р’В Р вЂ™Р’В Р В Р’В Р В РІР‚в„–Р В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРЎС™Р В Р’В Р вЂ™Р’В Р В Р’В Р В РІР‚в„–Р В Р’В Р вЂ™Р’В Р В Р’В Р Р†Р вЂљР’В° Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р вЂ™Р’В Р В Р вЂ Р В РІР‚С™Р вЂ™Р’В Р В Р’В Р вЂ™Р’В Р В Р’В Р В РІР‚в„–Р В Р’В Р В РІР‚В Р В Р’В Р Р†Р вЂљРЎв„ўР В Р вЂ Р Р†Р вЂљРЎвЂєР Р†Р вЂљРІР‚СљР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р Р†Р вЂљРЎСљР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р РЋРЎвЂєР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р Р†Р вЂљРІвЂћСћР В РІР‚в„ўР вЂ™Р’В»Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р вЂ™Р’В Р В Р вЂ Р В РІР‚С™Р вЂ™Р’В¦Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р вЂ™Р’ВР В Р’В Р вЂ™Р’В Р В Р’В Р В РІР‚в„–Р В Р’В Р В РІР‚В Р В Р’В Р Р†Р вЂљРЎв„ўР В Р Р‹Р Р†РІР‚С›РЎС›Р В Р’В Р вЂ™Р’В Р В Р’В Р В РІР‚в„–Р В Р’В Р вЂ™Р’В Р В Р’В Р Р†Р вЂљР’В° Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р РЋРЎС™Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р РЋРЎвЂєР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р В Р вЂ№Р В РІР‚в„ўР вЂ™Р’ВР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р Р†Р вЂљРІвЂћСћР В РІР‚в„ўР вЂ™Р’В°Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р вЂ™Р’В Р В Р вЂ Р В РІР‚С™Р вЂ™Р’В¦Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р РЋРЎвЂєР В Р вЂ Р В РІР‚С™Р вЂ™Р’ВР В Р’В Р вЂ™Р’В Р В Р’В Р В РІР‚в„–Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р РЋРЎв„ў. Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р В Р вЂ№Р В Р Р‹Р РЋРЎСџР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р РЋРЎвЂєР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р Р†Р вЂљРЎСљР В Р’В Р вЂ™Р’В Р В Р’В Р В РІР‚в„–Р В Р’В Р вЂ™Р’В Р В Р вЂ Р В РІР‚С™Р РЋРІвЂћСћР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р РЋРЎвЂєР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р Р†Р вЂљРІвЂћСћР В РІР‚в„ўР вЂ™Р’В±Р В Р’В Р вЂ™Р’В Р В Р’В Р В РІР‚в„–Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р РЋРЎв„ўР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р В РІР‚В Р В Р вЂ Р В РІР‚С™Р РЋРІР‚С”Р В Р вЂ Р В РІР‚С™Р Р†Р вЂљРЎС™ Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р Р†Р вЂљРІвЂћСћР В РІР‚в„ўР вЂ™Р’ВµР В Р’В Р вЂ™Р’В Р В Р’В Р В РІР‚в„–Р В Р’В Р В РІР‚В Р В Р’В Р Р†Р вЂљРЎв„ўР В РІР‚в„ўР вЂ™Р’В°Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р Р†Р вЂљРІвЂћСћР В РІР‚в„ўР вЂ™Р’Вµ Р В Р’В Р вЂ™Р’В Р В Р’В Р В РІР‚в„–Р В Р’В Р вЂ™Р’В Р В Р вЂ Р В РІР‚С™Р РЋРІвЂћСћР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р Р†Р вЂљРІвЂћСћР В РІР‚в„ўР вЂ™Р’В°Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р Р†Р вЂљРІвЂћСћР В РІР‚в„ўР вЂ™Р’В· Р В Р’В Р вЂ™Р’В Р В Р’В Р В РІР‚в„–Р В Р’В Р В РІР‚В Р В Р’В Р Р†Р вЂљРЎв„ўР В Р’В Р В РІР‚в„–Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р Р†Р вЂљРІвЂћСћР В РІР‚в„ўР вЂ™Р’ВµР В Р’В Р вЂ™Р’В Р В Р’В Р В РІР‚в„–Р В Р’В Р вЂ™Р’В Р В Р вЂ Р В РІР‚С™Р РЋРІвЂћСћР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р Р†Р вЂљРІвЂћСћР В РІР‚в„ўР вЂ™Р’ВµР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р Р†Р вЂљРІвЂћСћР В РІР‚в„ўР вЂ™Р’В· Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р В Р вЂ№Р В РІР‚в„ўР вЂ™Р’ВР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р вЂ™Р’ВР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р вЂ™Р’В Р В Р вЂ Р В РІР‚С™Р вЂ™Р’В¦Р В Р’В Р вЂ™Р’В Р В Р’В Р В РІР‚в„–Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р РЋРЎв„ўР В Р’В Р вЂ™Р’В Р В Р’В Р В РІР‚в„–Р В Р’В Р В РІР‚В Р В Р’В Р Р†Р вЂљРЎв„ўР В Р Р‹Р Р†РІР‚С›РЎС›Р В Р’В Р вЂ™Р’В Р В Р’В Р В РІР‚в„–Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р РЋРЎв„ў.")


def _render_list(items: list[dict[str, Any]], line_builder) -> str:
    if not items:
        return fix_mojibake("Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р В Р вЂ№Р В Р Р‹Р РЋРІвЂћСћР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р Р†Р вЂљРІвЂћСћР В РІР‚в„ўР вЂ™Р’ВµР В Р’В Р вЂ™Р’В Р В Р’В Р В РІР‚в„–Р В Р’В Р В РІР‚В Р В Р’В Р Р†Р вЂљРЎв„ўР В Р Р‹Р Р†РІР‚С›РЎС› Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р Р†Р вЂљРІвЂћСћР В РІР‚в„ўР вЂ™Р’В·Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р Р†Р вЂљРІвЂћСћР В РІР‚в„ўР вЂ™Р’В°Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р Р†Р вЂљРЎСљР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р вЂ™Р’ВР В Р’В Р вЂ™Р’В Р В Р’В Р В РІР‚в„–Р В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРЎС™Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р Р†Р вЂљРІвЂћСћР В РІР‚в„ўР вЂ™Р’ВµР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р В РІР‚В Р В Р вЂ Р В РІР‚С™Р РЋРІР‚С”Р В Р вЂ Р В РІР‚С™Р Р†Р вЂљРЎС™.")
    lines = [line_builder(item) for item in items]
    return "\n".join(lines[:50])


def _duplicate_cache_prune(now_monotonic: float) -> None:
    stale = [k for k, (ts, _) in _DUPLICATE_CACHE.items() if (now_monotonic - ts) > DUPLICATE_GUARD_TTL_S]
    for key in stale:
        _DUPLICATE_CACHE.pop(key, None)


def _duplicate_guard_get(cache_key: str) -> Any | None:
    now_monotonic = time.monotonic()
    with _DUPLICATE_CACHE_LOCK:
        _duplicate_cache_prune(now_monotonic)
        row = _DUPLICATE_CACHE.get(cache_key)
        if not row:
            return None
        ts, cached = row
        if (now_monotonic - ts) > DUPLICATE_GUARD_TTL_S:
            _DUPLICATE_CACHE.pop(cache_key, None)
            return None
        return cached


def _duplicate_guard_put(cache_key: str, response: Any) -> None:
    now_monotonic = time.monotonic()
    with _DUPLICATE_CACHE_LOCK:
        _duplicate_cache_prune(now_monotonic)
        _DUPLICATE_CACHE[cache_key] = (now_monotonic, response)


def _pref_key(name: str) -> str:
    return f"user_pref.{name}"


def _prefs_defaults() -> dict[str, str]:
    return {
        "language_mode": "ru",
        "voice_reply": "on",
        "brevity": "short",
    }


def _iter_user_pref_entries(user_id: int, limit: int = 400) -> list[dict[str, Any]]:
    settings = get_settings()
    session = SessionStore(settings.vault_path)
    return [item for item in session.get_recent(user_id, limit=limit) if item.get("type") == "user_pref"]


def get_user_preferences(user_id: int) -> dict[str, str]:
    prefs = _prefs_defaults()
    seen: set[str] = set()
    for item in reversed(_iter_user_pref_entries(user_id)):
        key = str(item.get("key") or "")
        value = str(item.get("value") or "").strip().lower()
        if key == _pref_key("language_mode") and "language_mode" not in seen and value in _VALID_LANGUAGE_MODES:
            prefs["language_mode"] = value
            seen.add("language_mode")
        elif key in {_pref_key("voice_reply"), "voice_reply_enabled"} and "voice_reply" not in seen:
            if value in {"1", "true", "on", "yes"}:
                prefs["voice_reply"] = "on"
                seen.add("voice_reply")
            elif value in {"0", "false", "off", "no"}:
                prefs["voice_reply"] = "off"
                seen.add("voice_reply")
        elif key == _pref_key("brevity") and "brevity" not in seen and value in _VALID_BREVITY:
            prefs["brevity"] = value
            seen.add("brevity")
    return prefs


def get_language_mode_preference(user_id: int) -> str:
    return get_user_preferences(user_id).get("language_mode", "ru")


def get_brevity_preference(user_id: int) -> str:
    return get_user_preferences(user_id).get("brevity", "short")


def _is_short_brevity(user_id: int) -> bool:
    return get_brevity_preference(user_id) == "short"


def _brevity_text(user_id: int, *, short: str, normal: str | None = None) -> str:
    if _is_short_brevity(user_id):
        return short
    return normal if normal is not None else short


def _set_user_preference(user_id: int, key: str, value: str | bool, *, source_ref: str | None = None) -> None:
    settings = get_settings()
    session = SessionStore(settings.vault_path)
    session.append(
        user_id,
        "user_pref",
        key=key,
        value=value,
        source_ref=source_ref or "openclaw",
    )


def _voice_pref_key() -> str:
    return _pref_key("voice_reply")


def get_voice_reply_preference(user_id: int) -> bool:
    return get_user_preferences(user_id).get("voice_reply", "on") == "on"


def set_voice_reply_preference(user_id: int, enabled: bool, *, source_ref: str | None = None) -> None:
    _set_user_preference(user_id, _voice_pref_key(), "on" if enabled else "off", source_ref=source_ref)


def set_language_mode_preference(user_id: int, mode: str, *, source_ref: str | None = None) -> None:
    normalized = str(mode or "").strip().lower()
    if normalized not in _VALID_LANGUAGE_MODES:
        raise ValueError("invalid_language_mode")
    _set_user_preference(user_id, _pref_key("language_mode"), normalized, source_ref=source_ref)


def set_brevity_preference(user_id: int, brevity: str, *, source_ref: str | None = None) -> None:
    normalized = str(brevity or "").strip().lower()
    if normalized not in _VALID_BREVITY:
        raise ValueError("invalid_brevity")
    _set_user_preference(user_id, _pref_key("brevity"), normalized, source_ref=source_ref)


def handle_prefs_status(user_id: int) -> str:
    started = time.perf_counter()
    prefs = get_user_preferences(user_id)
    text = (
        "Настройки:\n"
        f"- lang: {prefs.get('language_mode', 'ru')}\n"
        f"- voice: {prefs.get('voice_reply', 'on')}\n"
        f"- brevity: {prefs.get('brevity', 'short')}"
    )
    _log_handler_event(
        handler="handle_prefs_status",
        action="prefs_get",
        user_id=user_id,
        source="openclaw",
        status="ok",
        duration_ms=int((time.perf_counter() - started) * 1000),
    )
    return text


def handle_prefs_set(user_id: int, field: str, value: str, *, source_ref: str | None = None) -> str:
    started = time.perf_counter()
    key = str(field or "").strip().lower()
    normalized = str(value or "").strip().lower()
    if key == "voice":
        if normalized not in {"on", "off"}:
            _log_handler_event(handler="handle_prefs_set", action="prefs_set", user_id=user_id, source=str(source_ref or "openclaw"), status="error", error_type="invalid_usage", duration_ms=int((time.perf_counter() - started) * 1000))
            return USAGE_PREFS
        text = handle_voice_set(user_id, normalized == "on", source_ref=source_ref)
        _log_handler_event(handler="handle_prefs_set", action="prefs_set", user_id=user_id, source=str(source_ref or "openclaw"), status="ok", duration_ms=int((time.perf_counter() - started) * 1000))
        return text
    if key == "lang":
        if normalized not in _VALID_LANGUAGE_MODES:
            _log_handler_event(handler="handle_prefs_set", action="prefs_set", user_id=user_id, source=str(source_ref or "openclaw"), status="error", error_type="invalid_usage", duration_ms=int((time.perf_counter() - started) * 1000))
            return USAGE_PREFS
        set_language_mode_preference(user_id, normalized, source_ref=source_ref)
        _log_handler_event(handler="handle_prefs_set", action="prefs_set", user_id=user_id, source=str(source_ref or "openclaw"), status="ok", duration_ms=int((time.perf_counter() - started) * 1000))
        return f"Language mode: {normalized}."
    if key == "brevity":
        if normalized not in _VALID_BREVITY:
            _log_handler_event(handler="handle_prefs_set", action="prefs_set", user_id=user_id, source=str(source_ref or "openclaw"), status="error", error_type="invalid_usage", duration_ms=int((time.perf_counter() - started) * 1000))
            return USAGE_PREFS
        set_brevity_preference(user_id, normalized, source_ref=source_ref)
        _log_handler_event(handler="handle_prefs_set", action="prefs_set", user_id=user_id, source=str(source_ref or "openclaw"), status="ok", duration_ms=int((time.perf_counter() - started) * 1000))
        return f"Brevity: {normalized}."
    _log_handler_event(handler="handle_prefs_set", action="prefs_set", user_id=user_id, source=str(source_ref or "openclaw"), status="error", error_type="invalid_usage", duration_ms=int((time.perf_counter() - started) * 1000))
    return USAGE_PREFS


def _log_degraded_handler(
    *,
    handler: str,
    user_id: int,
    source_ref: str | None,
    error_type: str,
    error_message: str = "",
) -> None:
    _obs_record_error(
        handler=handler,
        error_type=error_type,
        source=str(source_ref or "openclaw"),
        user_id=user_id,
    )
    logger.warning(
        "%s",
        json.dumps(
            {
                "event": "openclaw_bridge_degraded",
                "handler": handler,
                "user_id": user_id,
                "source_ref": source_ref or "openclaw",
                "source": source_ref or "openclaw",
                "action": handler,
                "status": "degraded",
                "error_type": error_type,
                "error_message": _sanitize_text_for_logs(error_message, max_len=300),
                "degraded": True,
                "duration_ms": 0,
            },
            ensure_ascii=True,
            separators=(",", ":"),
        ),
    )


def _sidecar_degraded_fallback_text(user_id: int) -> str:
    return _brevity_text(
        user_id,
        short="Сервис временно недоступен.",
        normal="Сервис временно недоступен. Попробуйте позже.",
    )


def _log_handler_event(
    *,
    handler: str,
    action: str,
    user_id: int | None,
    source: str,
    status: str,
    duration_ms: int = 0,
    error_type: str | None = None,
) -> None:
    if status in {"error", "degraded"} and error_type:
        _obs_record_error(
            handler=handler,
            error_type=error_type,
            source=source,
            user_id=user_id,
        )
    logger.info(
        "%s",
        json.dumps(
            {
                "event": "openclaw_bridge_handler",
                "handler": handler,
                "action": action,
                "user_id": int(user_id or 0),
                "source": source,
                "status": status,
                "error_type": error_type or "",
                "duration_ms": int(duration_ms),
            },
            ensure_ascii=True,
            separators=(",", ":"),
        ),
    )


def _get_git_commit_short() -> str:
    global _GIT_COMMIT_CACHE
    if _GIT_COMMIT_CACHE is not None:
        return _GIT_COMMIT_CACHE
    try:
        repo_root = Path(__file__).resolve().parents[3]
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(repo_root),
            stderr=subprocess.DEVNULL,
            timeout=BRIDGE_GIT_TIMEOUT_S,
            text=True,
        ).strip()
        _GIT_COMMIT_CACHE = out or "unknown"
    except Exception:
        _GIT_COMMIT_CACHE = "unknown"
    return _GIT_COMMIT_CACHE


def _probe_sidecar_availability(user_id: int, source_ref: str | None = None) -> dict[str, Any]:
    started = time.perf_counter()
    result = _call_sidecar_action_guarded(
        handler_name="diag_sidecar_probe",
        action="event_list",
        payload={"status": "planned", "limit": 1, "offset": 0},
        user_id=user_id,
        source_ref=source_ref or "openclaw:diag",
        timeout_s=BRIDGE_DIAG_SIDECAR_PROBE_TIMEOUT_S,
    )
    duration_ms = int((time.perf_counter() - started) * 1000)
    if result is None:
        return {"available": False, "status": "timeout_or_error", "duration_ms": duration_ms, "error": "degraded"}
    return {
        "available": True,
        "status": str(result.status or "unknown"),
        "duration_ms": duration_ms,
        "error": str(result.error_code or ""),
    }


def _call_sidecar_action_guarded(
    *,
    handler_name: str,
    action: str,
    payload: dict[str, Any] | None,
    user_id: int,
    source_ref: str | None = None,
    timeout_s: float | None = None,
):
    effective_timeout_s = float(timeout_s if timeout_s is not None else SIDECAR_CALL_TIMEOUT_S)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                call_sidecar_action,
                action,
                payload,
                user_id,
                "openclaw",
            )
            return future.result(timeout=effective_timeout_s)
    except FuturesTimeoutError:
        _log_degraded_handler(
            handler=handler_name,
            user_id=user_id,
            source_ref=source_ref,
            error_type="sidecar_timeout",
            error_message=f"timeout>{effective_timeout_s}s",
        )
        return None
    except Exception as exc:
        _log_degraded_handler(
            handler=handler_name,
            user_id=user_id,
            source_ref=source_ref,
            error_type=type(exc).__name__,
            error_message=_sanitize_text_for_logs(exc, max_len=300),
        )
        return None


def handle_status(user_id: int) -> str:
    settings = get_settings()
    session = SessionStore(settings.vault_path)
    session.append(user_id, "command", cmd="/status")
    mode = _detect_mode(user_id)
    mode_label = "english_tutor" if mode == "tutor" else ("reflection" if mode == "reflection" else "default")
    tts_provider = (settings.tts_provider or "").strip().lower()
    tts_on = tts_provider not in {"", "none"}
    return (
        "Статус: готов.\n"
        f"Режим: {mode_label}\n"
        f"TTS: {'on' if tts_on else 'off'}"
        + (f" ({tts_provider})" if tts_on else "")
    )


def handle_help(user_id: int | None = None) -> str:
    brevity_short = bool(user_id is not None and _is_short_brevity(user_id))
    return (
        "Команды (MVP):\n"
        "/help\n"
        "/ping\n"
        "/version\n"
        "/status\n"
        "/mode\n"
        "/prefs\n"
        "/prefs brevity short|normal\n"
        "/prefs lang ru|en_tutor\n"
        "/prefs voice on|off\n"
        "/voice status|on|off\n"
        "/plan add <title>\n"
        "/plan list\n"
        "/plan done <id>\n"
        "/plan delete <id>\n"
        + (
            ""
            if brevity_short
            else "Голос/текст без команды: авто-маршрут (обычный/тьютор/рефлексия)."
        )
    )


def handle_health(user_id: int | None = None) -> str:
    _ = user_id
    snap = get_health_snapshot()
    checks = snap.get("checks") or {}
    workspace_ok = bool((checks.get("workspace_exists") or {}).get("ok"))
    bootstrap_ok = bool((checks.get("bootstrap_exists") or {}).get("ok"))
    heartbeat_ok = bool((checks.get("heartbeat_exists") or {}).get("ok"))
    vault_ok = bool((checks.get("vault_path_exists") or {}).get("ok"))
    mode_details = (checks.get("openclaw_mode_expected") or {}).get("details") or {}
    mode_text = "OpenClaw" if bool(mode_details.get("telegram_disabled")) else "local aiogram requested"
    icon = "OK" if bool(snap.get("ok")) else "WARN"
    return (
        f"{icon} Health\n"
        f"warnings: {len(snap.get('warnings') or [])}\n"
        f"errors: {len(snap.get('errors') or [])}\n"
        f"gateway mode: {mode_text}\n"
        f"workspace: {'ok' if workspace_ok else 'fail'}\n"
        f"bootstrap/heartbeat: {'ok' if (bootstrap_ok and heartbeat_ok) else 'fail'}\n"
        f"vault: {'ok' if vault_ok else 'fail'}"
    )


def handle_diag(user_id: int | None = None, *, full: bool = False, source_ref: str | None = None) -> str:
    started = time.perf_counter()
    base = handle_health(user_id)
    snap = get_health_snapshot()
    errors = {str(item) for item in (snap.get("errors") or [])}
    warnings = {str(item) for item in (snap.get("warnings") or [])}
    tips: list[str] = []
    if {"bootstrap_missing", "heartbeat_missing"} & errors:
        tips.append("Tip: check .openclaw/workspace/bootstrap.md and heartbeat.md")
    if {"bridge_import_failed", "bridge_import_incomplete"} & errors:
        tips.append("Tip: verify .venv activation and src import path")
    if "telegram_disabled_false" in warnings:
        tips.append("Tip: set D_BRAIN_TELEGRAM_DISABLED=1 in production")
    if "single_poller_conflict_risk" in warnings:
        tips.append("Tip: stop python/openclaw duplicate pollers, then run ops\\restart-openclaw.ps1")
    if not tips:
        tips.append("Tip: run scripts/openclaw_prod_diag.py for extended checks")
    user_val = int(user_id or 0)
    prefs = get_user_preferences(user_val) if user_id is not None else _prefs_defaults()
    settings = get_settings()
    obs = get_runtime_observability_snapshot()
    sidecar_probe = _probe_sidecar_availability(user_val, source_ref=source_ref)
    tts_provider = (settings.tts_provider or "").strip().lower()
    stt_provider = (settings.stt_provider or "").strip().lower()
    short_lines = [
        "DIAG",
        f"transport: openclaw",
        "build: openclaw-bridge",
        f"version: {D_BRAIN_VERSION}",
        f"prefs: {prefs.get('language_mode')}/{prefs.get('voice_reply')}/{prefs.get('brevity')}",
        f"voice: stt={'on' if stt_provider not in {'', 'none'} else 'off'} tts={'on' if tts_provider not in {'', 'none'} else 'off'}",
        f"sidecar: {'ok' if sidecar_probe.get('available') else 'degraded'} ({sidecar_probe.get('status')}, {sidecar_probe.get('duration_ms')}ms)",
        f"errors: {sum((obs.get('error_counts_by_type') or {}).values())} last={obs.get('last_error_at') or '-'}",
        f"uptime_s: {obs.get('uptime_s', 0)}",
    ]
    if not full:
        text = "\n".join(short_lines)
        _log_handler_event(handler="handle_diag", action="diag", user_id=user_id, source=str(source_ref or "openclaw"), status="ok", duration_ms=int((time.perf_counter() - started) * 1000))
        return text
    error_counts = obs.get("error_counts_by_type") or {}
    top_errors = ", ".join(
        f"{name}:{count}" for name, count in sorted(error_counts.items(), key=lambda item: (-item[1], item[0]))[:5]
    ) or "-"
    recent = obs.get("recent_errors") or []
    recent_lines = [
        f"- {row.get('ts')} {row.get('handler')} {row.get('error_type')}" for row in recent[-5:]
    ] or ["- none"]
    full_text = (
        "\n".join(short_lines)
        + "\n"
        + f"commit: {_get_git_commit_short()}\n"
        + f"process_start: {obs.get('process_start_utc')}\n"
        + f"timeouts_s: sidecar={SIDECAR_CALL_TIMEOUT_S} diag_probe={BRIDGE_DIAG_SIDECAR_PROBE_TIMEOUT_S} stt={BRIDGE_STT_TIMEOUT_S} tts={BRIDGE_TTS_TIMEOUT_S}\n"
        + f"sidecar_error: {sidecar_probe.get('error') or '-'}\n"
        + f"top_errors: {top_errors}\n"
        + "recent_errors:\n"
        + "\n".join(recent_lines)
        + "\n"
        + "\n".join(tips[:3])
    )
    _log_handler_event(handler="handle_diag", action="diag_full", user_id=user_id, source=str(source_ref or "openclaw"), status="ok", duration_ms=int((time.perf_counter() - started) * 1000))
    return full_text


def handle_plan_add(
    user_id: int,
    title: str,
    *,
    source_ref: str | None = None,
) -> str:
    started = time.perf_counter()
    payload = {
        "title": title,
        "source_type": "openclaw",
        "source_ref": source_ref or "openclaw",
    }
    result = _call_sidecar_action_guarded(
        handler_name="handle_plan_add",
        action="event_create",
        payload=payload,
        user_id=user_id,
        source_ref=source_ref,
    )
    if result is None:
        _log_handler_event(handler="handle_plan_add", action="plan_add", user_id=user_id, source=str(source_ref or "openclaw"), status="degraded", error_type="sidecar_timeout_or_error", duration_ms=int((time.perf_counter() - started) * 1000))
        return _sidecar_degraded_fallback_text(user_id)
    if result.status != "ok":
        _log_handler_event(handler="handle_plan_add", action="plan_add", user_id=user_id, source=str(source_ref or "openclaw"), status="error", error_type=str(result.error_code or "sidecar_error"), duration_ms=int((time.perf_counter() - started) * 1000))
        return _format_error(result.error_code, result.error_message)
    event_id = result.data.get("event_id") if result.data else None
    _log_handler_event(handler="handle_plan_add", action="plan_add", user_id=user_id, source=str(source_ref or "openclaw"), status="ok", duration_ms=int((time.perf_counter() - started) * 1000))
    return f"Создано: #{event_id}."


def handle_plan_list(user_id: int) -> str:
    started = time.perf_counter()
    result = _call_sidecar_action_guarded(
        handler_name="handle_plan_list",
        action="event_list",
        payload={"status": "planned", "limit": 50, "offset": 0},
        user_id=user_id,
        source_ref="openclaw:command",
    )
    if result is None:
        _log_handler_event(handler="handle_plan_list", action="plan_list", user_id=user_id, source="openclaw:command", status="degraded", error_type="sidecar_timeout_or_error", duration_ms=int((time.perf_counter() - started) * 1000))
        return _sidecar_degraded_fallback_text(user_id)
    if result.status != "ok":
        _log_handler_event(handler="handle_plan_list", action="plan_list", user_id=user_id, source="openclaw:command", status="error", error_type=str(result.error_code or "sidecar_error"), duration_ms=int((time.perf_counter() - started) * 1000))
        return _format_error(result.error_code, result.error_message)
    events = (result.data or {}).get("events", [])
    if not events:
        _log_handler_event(handler="handle_plan_list", action="plan_list", user_id=user_id, source="openclaw:command", status="ok", duration_ms=int((time.perf_counter() - started) * 1000))
        return "Нет планов."
    visible = list(events[:PLAN_LIST_MAX_DISPLAY])
    lines = [f"{idx}. #{item['id']} {item['title']}" for idx, item in enumerate(visible, start=1)]
    hidden_count = max(len(events) - len(visible), 0)
    if hidden_count > 0:
        lines.append(f"И ещё {hidden_count}.")
    _log_handler_event(handler="handle_plan_list", action="plan_list", user_id=user_id, source="openclaw:command", status="ok", duration_ms=int((time.perf_counter() - started) * 1000))
    return "\n".join(lines)


def _parse_plan_command_id(normalized: str, prefix: str, usage_text: str) -> tuple[int | None, str | None]:
    raw = normalized[len(prefix) :].strip()
    if not raw:
        return None, usage_text
    if not raw.isdigit():
        return None, "ID должен быть числом."
    return int(raw), None


def _handle_plan_status_change(user_id: int, event_id: int, status: str) -> str:
    result = _call_sidecar_action_guarded(
        handler_name="handle_plan_status_change",
        action="event_update_status",
        payload={"event_id": int(event_id), "status": status},
        user_id=user_id,
        source_ref="openclaw:command",
    )
    if result is None:
        return _sidecar_degraded_fallback_text(user_id)
    if result.status != "ok":
        if str(result.error_code or "") == "not_found":
            return f"Не найдено: #{event_id}."
        return _format_error(result.error_code, result.error_message)
    if status == "done":
        return f"Готово: #{event_id} отмечен выполненным."
    if status == "canceled":
        return f"Удалено: #{event_id}."
    return f"Обновлено: #{event_id}."


def handle_plan_done(user_id: int, event_id: int) -> str:
    return _handle_plan_status_change(user_id, event_id, "done")


def handle_plan_delete(user_id: int, event_id: int) -> str:
    # MVP delete is a soft-delete via canceled status to reuse the existing event lifecycle.
    return _handle_plan_status_change(user_id, event_id, "canceled")


def handle_mode(user_id: int) -> str:
    settings = get_settings()
    prefs = get_user_preferences(user_id)
    raw_mode = _detect_mode(user_id)
    mode_label = "english_tutor" if raw_mode == "tutor" else ("reflection" if raw_mode == "reflection" else "default")
    tts_provider = (settings.tts_provider or "").strip().lower()
    tts_on = tts_provider not in {"", "none"}
    return (
        "Режимы:\n"
        f"- mode: {mode_label}\n"
        f"- language_mode: {prefs.get('language_mode')}\n"
        f"- voice_reply: {prefs.get('voice_reply')}\n"
        f"- brevity: {prefs.get('brevity')}\n"
        f"- tts: {'on' if tts_on else 'off'}"
        + (f" ({tts_provider})" if tts_on else "")
    )


def handle_voice_status(user_id: int) -> str:
    return f"Голосовой ответ: {'вкл' if get_voice_reply_preference(user_id) else 'выкл'}."


def handle_voice_set(user_id: int, enabled: bool, *, source_ref: str | None = None) -> str:
    set_voice_reply_preference(user_id, enabled, source_ref=source_ref)
    return f"Голосовой ответ: {'вкл' if enabled else 'выкл'}."


def handle_ping(user_id: int, source_ref: str | None = None) -> str:
    started = time.perf_counter()
    settings = get_settings()
    route = resolve_route(TASK_COMMAND_STATUS, settings)
    mode = _detect_mode(user_id)
    mode_label = "english_tutor" if mode == "tutor" else ("reflection" if mode == "reflection" else "default")
    provider = route.selected_provider or "deterministic"
    model = route.selected_model or ""
    parts = [f"pong mode={mode_label}", f"provider={provider}"]
    if model:
        parts.append(f"model={model}")
    if source_ref:
        parts.append(f"src={source_ref}")
    parts.append(f"t={int((time.perf_counter() - started) * 1000)}ms")
    text = " | ".join(parts[:5])
    _log_handler_event(handler="handle_ping", action="ping", user_id=user_id, source=str(source_ref or "openclaw"), status="ok", duration_ms=int((time.perf_counter() - started) * 1000))
    return text


def handle_version(user_id: int, source_ref: str | None = None) -> str:
    _ = user_id, source_ref
    started = time.perf_counter()
    ts = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    text = (
        f"version={D_BRAIN_VERSION}\n"
        "build=openclaw-bridge\n"
        f"commit={_get_git_commit_short()}\n"
        "transport=openclaw\n"
        f"time={ts}"
    )
    _log_handler_event(handler="handle_version", action="version", user_id=user_id, source=str(source_ref or "openclaw"), status="ok", duration_ms=int((time.perf_counter() - started) * 1000))
    return text


def handle_hb_now() -> str:
    result = build_scheduler_adapter().run_job_now(JOB_HEARTBEAT_TICK)
    payload = result.payload
    status = str(payload.get("status") or result.status or "unknown")
    provider = str(payload.get("provider") or "")
    fallback = bool(payload.get("fallback_used"))
    if result.ok:
        return f"Heartbeat \u0432\u044b\u043f\u043e\u043b\u043d\u0435\u043d. status={status} provider={provider} fallback={fallback}"
    reason = str(payload.get("reason") or payload.get("message") or payload.get("error") or "unknown")
    return (
        "Heartbeat \u0432\u044b\u043f\u043e\u043b\u043d\u0435\u043d "
        f"\u0441 \u043f\u0440\u0435\u0434\u0443\u043f\u0440\u0435\u0436\u0434\u0435\u043d\u0438\u0435\u043c. status={status} "
        f"provider={provider} reason={reason}"
    )


def handle_hb_interval(minutes_raw: str) -> str:
    if not minutes_raw.isdigit():
        return USAGE_HB
    minutes = int(minutes_raw)
    updated = set_heartbeat_interval(minutes)
    if not updated.get("ok"):
        return (
            f"\u0418\u043d\u0442\u0435\u0440\u0432\u0430\u043b \u0434\u043e\u043b\u0436\u0435\u043d "
            f"\u0431\u044b\u0442\u044c {HEARTBEAT_INTERVAL_MIN}..{HEARTBEAT_INTERVAL_MAX} \u043c\u0438\u043d."
        )
    sync = build_scheduler_adapter().sync_jobs(build_job_specs(), trigger_source="manual_bridge")
    return (
        f"Heartbeat interval={minutes} \u043c\u0438\u043d. "
        f"sync={sync.get('status')} mode={sync.get('execution_mode')}"
    )


def handle_hb_toggle(enabled: bool) -> str:
    set_heartbeat_enabled(enabled)
    sync = build_scheduler_adapter().sync_jobs(build_job_specs(), trigger_source="manual_bridge")
    state = "on" if enabled else "off"
    return (
        f"Heartbeat {state}. sync={sync.get('status')} mode={sync.get('execution_mode')}"
    )


def handle_hb_status() -> str:
    state = get_heartbeat_status()
    return (
        "\u0421\u0442\u0430\u0442\u0443\u0441 heartbeat\n"
        f"last_run_at={state.get('last_run_at', '')}\n"
        f"last_status={state.get('last_status', 'never')}\n"
        f"last_provider={state.get('last_provider', '')}\n"
        f"last_model={state.get('last_model', '')}\n"
        f"last_trigger={state.get('last_trigger', '')}\n"
        f"last_job_name={state.get('last_job_name', '')}\n"
        f"last_duration_ms={state.get('last_duration_ms', 0)}\n"
        f"last_fallback={bool(state.get('last_fallback_used', False))}\n"
        f"last_error={state.get('last_error', '')}"
    )


def handle_digest_toggle(enabled: bool) -> str:
    set_digest_enabled(enabled)
    sync = build_scheduler_adapter().sync_jobs(build_job_specs(), trigger_source="manual_bridge")
    state = "on" if enabled else "off"
    return f"Digest {state}. sync={sync.get('status')} mode={sync.get('execution_mode')}"


def handle_digest_time(value: str) -> str:
    updated = set_digest_time(value)
    if not updated.get("ok"):
        return USAGE_DIGEST
    sync = build_scheduler_adapter().sync_jobs(build_job_specs(), trigger_source="manual_bridge")
    return f"Digest time={value}. sync={sync.get('status')} mode={sync.get('execution_mode')}"


def handle_digest_now() -> str:
    result = run_digest_daily_sync(
        trigger_source="manual_bridge",
        job_name=JOB_DIGEST_DAILY,
        persist=True,
        preview_only=False,
        deliver_to_target=False,
    )
    text = str(result.get("text") or "").strip()
    if text:
        return text
    return "Р В РІР‚СњР В Р’В°Р В РІвЂћвЂ“Р В РўвЂР В Р’В¶Р В Р’ВµР РЋР С“Р РЋРІР‚С™ Р В РЎвЂ”Р В РЎвЂўР В РЎвЂќР В Р’В° Р В Р вЂ¦Р В Р’ВµР В РўвЂР В РЎвЂўР РЋР С“Р РЋРІР‚С™Р РЋРЎвЂњР В РЎвЂ”Р В Р’ВµР В Р вЂ¦. Р В РЎСџР В РЎвЂўР В РЎвЂ”Р РЋР вЂљР В РЎвЂўР В Р’В±Р РЋРЎвЂњР В РІвЂћвЂ“Р РЋРІР‚С™Р В Р’Вµ Р В РЎвЂ”Р В РЎвЂўР В Р’В·Р В Р’В¶Р В Р’Вµ."


def handle_digest_preview() -> str:
    result = run_digest_daily_sync(
        trigger_source="manual_preview",
        job_name=JOB_DIGEST_DAILY,
        persist=False,
        preview_only=True,
        deliver_to_target=False,
    )
    text = str(result.get("text") or "").strip()
    if not text:
        return "Р В РЎСџР РЋР вЂљР В Р’ВµР В Р вЂ Р РЋР Р‰Р РЋР вЂ№ Р В РўвЂР В Р’В°Р В РІвЂћвЂ“Р В РўвЂР В Р’В¶Р В Р’ВµР РЋР С“Р РЋРІР‚С™Р В Р’В° Р В Р вЂ¦Р В Р’ВµР В РўвЂР В РЎвЂўР РЋР С“Р РЋРІР‚С™Р РЋРЎвЂњР В РЎвЂ”Р В Р вЂ¦Р В РЎвЂў."
    return "Р В РЎСџР РЋР вЂљР В Р’ВµР В Р вЂ Р РЋР Р‰Р РЋР вЂ№ Р В РўвЂР В Р’В°Р В РІвЂћвЂ“Р В РўвЂР В Р’В¶Р В Р’ВµР РЋР С“Р РЋРІР‚С™Р В Р’В°:\n" + text


def handle_digest_status() -> str:
    status = get_digest_status()
    return (
        "Digest status\n"
        f"enabled={bool(status.get('enabled'))}\n"
        f"time={status.get('time', '')}\n"
        f"last_run_at={status.get('last_run_at', '')}\n"
        f"last_status={status.get('last_status', 'never')}\n"
        f"last_trigger={status.get('last_trigger', '')}\n"
        f"source={status.get('last_source', '')}\n"
        f"delivery={status.get('last_delivery_state', '')}\n"
        f"delivery_error={status.get('last_delivery_error', '')}\n"
        f"warnings={len(status.get('last_warnings') or [])}"
    )


def _chat_id_from_source_ref(source_ref: str | None) -> int | None:
    if not source_ref:
        return None
    left = str(source_ref).split(":", 1)[0].strip()
    if left.isdigit():
        return int(left)
    return None


def handle_digest_status_for_user(user_id: int) -> str:
    status = get_digest_status()
    target = get_digest_target(user_id)
    target_enabled = bool(target.get("enabled")) if target else False
    target_channel = str(target.get("channel")) if target else ""
    target_chat_id = str(target.get("chat_id")) if target else ""
    target_configured = target is not None and bool(target_chat_id)
    target_view = f"{target_channel}:{target_chat_id}" if target_configured else NOT_CONFIGURED_RU
    last_delivery = str(status.get("last_delivery_state") or "")
    if not last_delivery:
        last_delivery = "never"
    return (
        "\u0421\u0442\u0430\u0442\u0443\u0441 digest\n"
        f"enabled={bool(status.get('enabled'))}\n"
        f"time={status.get('time', '')}\n"
        f"target_configured={target_configured}\n"
        f"target_enabled={target_enabled}\n"
        f"target={target_view}\n"
        f"target_channel={target_channel or '-'}\n"
        f"target_chat_id={target_chat_id or '-'}\n"
        f"last_run_at={status.get('last_run_at', '')}\n"
        f"last_status={status.get('last_status', 'never')}\n"
        f"last_trigger={status.get('last_trigger', '')}\n"
        f"source={status.get('last_source', '')}\n"
        f"delivery={last_delivery}\n"
        f"delivery_error={status.get('last_delivery_error', '')}\n"
        f"warnings={len(status.get('last_warnings') or [])}"
    )


def handle_digest_target_here(user_id: int, source_ref: str | None) -> str:
    chat_id = _chat_id_from_source_ref(source_ref)
    if chat_id is None:
        return (
            "\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u043e\u043f\u0440\u0435\u0434\u0435\u043b\u0438\u0442\u044c chat_id.\n"
            + USAGE_DIGEST_TARGET
        )
    target = set_digest_target(
        user_id,
        channel="telegram",
        chat_id=chat_id,
        enabled=True,
        label="openclaw",
    )
    return f"\u0426\u0435\u043b\u044c digest \u0441\u043e\u0445\u0440\u0430\u043d\u0435\u043d\u0430: channel={target.get('channel')} chat_id={target.get('chat_id')}"


def handle_digest_target_show(user_id: int) -> str:
    target = get_digest_target(user_id)
    if not target:
        return NOT_CONFIGURED_RU
    return (
        "\u0426\u0435\u043b\u044c digest\n"
        f"channel={target.get('channel')}\n"
        f"chat_id={target.get('chat_id')}\n"
        f"enabled={bool(target.get('enabled'))}"
    )


def handle_digest_target_toggle(user_id: int, enabled: bool) -> str:
    target = set_digest_target_enabled(user_id, enabled=enabled)
    if not target:
        return NOT_CONFIGURED_RU
    state = "on" if enabled else "off"
    return f"Digest target {state}. channel={target.get('channel')} chat_id={target.get('chat_id')}"


def handle_digest_target_clear(user_id: int) -> str:
    removed = clear_digest_target(user_id)
    if not removed:
        return NOT_CONFIGURED_RU
    return "\u0426\u0435\u043b\u044c digest \u0443\u0434\u0430\u043b\u0435\u043d\u0430."


def handle_digest_target_test(user_id: int) -> str:
    target = get_digest_target(user_id)
    if not target or not target.get("enabled"):
        return NOT_CONFIGURED_RU
    send_result = build_openclaw_outbound().send_text(
        channel=str(target.get("channel") or "telegram"),
        target=str(target.get("chat_id") or ""),
        text="\u0422\u0435\u0441\u0442 digest target",
        trigger="manual",
        provider_role="cron",
    )
    state = str(send_result.delivery_state or "")
    if state == "sent":
        return f"\u0422\u0435\u0441\u0442 \u043e\u0442\u043f\u0440\u0430\u0432\u043b\u0435\u043d. channel={send_result.channel} chat_id={send_result.target}"
    if state == "deferred":
        return "\u0422\u0435\u0441\u0442 \u043e\u0442\u043b\u043e\u0436\u0435\u043d (stub_fallback)."
    return f"\u0422\u0435\u0441\u0442 \u043d\u0435 \u043e\u0442\u043f\u0440\u0430\u0432\u043b\u0435\u043d. state={state} error={send_result.error or ''}"

def handle_cron_sync() -> str:
    sync = build_scheduler_adapter().sync_jobs(build_job_specs(), trigger_source="manual_bridge")
    return (
        f"Cron sync status={sync.get('status')} "
        f"jobs={len(sync.get('jobs') or [])} mode={sync.get('execution_mode')}"
    )


def handle_cron_list() -> str:
    config = get_scheduler_config()
    jobs = build_scheduler_adapter().list_jobs()
    if not jobs:
        return "\u041d\u0435\u0442 \u0434\u043e\u0441\u0442\u0443\u043f\u043d\u044b\u0445 cron-\u0437\u0430\u0434\u0430\u0447."
    lines = ["Cron-\u0437\u0430\u0434\u0430\u0447\u0438:"]
    lines.append(
        f"- heartbeat.tick configured: enabled={bool(config['heartbeat']['enabled'])} interval={config['heartbeat']['interval_minutes']}m"
    )
    lines.append(
        f"- digest.daily configured: enabled={bool(config['digest']['enabled'])} time={config['digest']['time']}"
    )
    lines.append("Adapter view:")
    for job in jobs:
        status = "enabled" if bool(job.get("enabled", True)) else "disabled"
        schedule_kind = str(job.get("schedule_kind") or "")
        schedule_value = str(job.get("schedule_value") or "")
        if schedule_kind and schedule_value:
            lines.append(f"- {job.get('name', '')} ({status}) {schedule_kind}={schedule_value}")
        else:
            lines.append(f"- {job.get('name', '')} ({status})")
    return "\n".join(lines)


def handle_cron_run(job_name: str, *, user_id: int) -> str:
    adapter = build_scheduler_adapter()
    if job_name == JOB_DIGEST_DAILY:
        result = adapter.run_job_scheduled(job_name, user_id=user_id)
    else:
        result = adapter.run_job_now(job_name, user_id=user_id)
    payload = result.payload
    if result.ok:
        delivery_suffix = ""
        if job_name == JOB_DIGEST_DAILY:
            delivery_suffix = (
                f" delivery={payload.get('delivery', '')}"
                f" target_resolved={bool(payload.get('target_resolved', False))}"
            )
        return (
            f"Cron job \u0432\u044b\u043f\u043e\u043b\u043d\u0435\u043d. job={payload.get('job')} "
            f"provider={payload.get('provider')} fallback={bool(payload.get('fallback_used'))}"
            f"{delivery_suffix}"
        )
    error = str(payload.get("error") or "unknown")
    if error == "job_not_registered":
        return f"\u041d\u0435\u0438\u0437\u0432\u0435\u0441\u0442\u043d\u0430\u044f cron-\u0437\u0430\u0434\u0430\u0447\u0430: {job_name}\n{USAGE_CRON}"
    reason = str(payload.get("reason") or "")
    return (
        f"Cron job \u043d\u0435 \u0432\u044b\u043f\u043e\u043b\u043d\u0435\u043d. job={payload.get('job')} error={error}"
        + (f" reason={reason}" if reason else "")
    )


def _log_command_route(user_id: int, source_ref: str | None):
    route = resolve_route(TASK_COMMAND_STATUS, get_settings())
    logger.info(
        "Model routing: channel=command source_ref=%s user_id=%s task_type=%s provider=%s model=%s fallback_used=%s allowed=%s reason=%s",
        source_ref or "openclaw",
        user_id,
        route.task_type,
        route.selected_provider,
        route.selected_model,
        route.fallback_used,
        route.allowed,
        route.reason or "",
    )
    return route


def dispatch_command(
    text: str,
    *,
    user_id: int,
    source_ref: str | None = None,
    request_id: str | None = None,
) -> str | None:
    req_id = _short_request_id(request_id)
    normalized = " ".join((text or "").strip().split())
    if not normalized:
        return None
    if normalized.startswith("/") and len(normalized) > MAX_COMMAND_TEXT_CHARS:
        return _brevity_text(
            user_id,
            short="Слишком длинная команда.",
            normal="Слишком длинная команда. Сократите текст и попробуйте снова.",
        )
    prefs = get_user_preferences(user_id)
    command_language = "en" if prefs.get("language_mode") == "en_tutor" else "ru"
    try:
        ingest_message_event(
            {
                "source_type": "command",
                "user_id": str(user_id),
                "channel": "openclaw",
                "source_ref": source_ref or "openclaw:command",
                "text": normalized,
                "language": command_language,
                "tags": ["bridge", "command"],
                "importance": "normal",
                "needs_indexing": False,
            }
        )
    except Exception:
        pass

    lowered = normalized.lower()
    if lowered.startswith("/help "):
        return "Использование: /help"
    if lowered.startswith("/status "):
        return "Использование: /status"
    if lowered.startswith("/ping "):
        return "Использование: /ping"
    if lowered.startswith("/version "):
        return "Использование: /version"
    if lowered.startswith("/diag ") and lowered != "/diag full":
        return "Использование: /diag | /diag full"
    if lowered == "/health":
        started = time.perf_counter()
        result = handle_health(user_id)
        _log_bridge_event(
            route="command",
            user_id=user_id,
            source_ref=str(source_ref or "openclaw:command"),
            handler="dispatch_command:/health",
            ok=True,
            latency_ms=int((time.perf_counter() - started) * 1000),
            fallback_used=False,
            error_code="",
            request_id=req_id,
        )
        return result
    if lowered == "/diag":
        started = time.perf_counter()
        result = handle_diag(user_id, full=False, source_ref=source_ref)
        _log_bridge_event(
            route="command",
            user_id=user_id,
            source_ref=str(source_ref or "openclaw:command"),
            handler="dispatch_command:/diag",
            ok=True,
            latency_ms=int((time.perf_counter() - started) * 1000),
            fallback_used=False,
            error_code="",
            request_id=req_id,
        )
        return result
    if lowered == "/diag full":
        started = time.perf_counter()
        result = handle_diag(user_id, full=True, source_ref=source_ref)
        _log_bridge_event(
            route="command",
            user_id=user_id,
            source_ref=str(source_ref or "openclaw:command"),
            handler="dispatch_command:/diag full",
            ok=True,
            latency_ms=int((time.perf_counter() - started) * 1000),
            fallback_used=False,
            error_code="",
            request_id=req_id,
        )
        return result
    if lowered == "/ping":
        route = _log_command_route(user_id, source_ref)
        if not route.allowed:
            return COMMAND_ROUTE_UNAVAILABLE_RU
        return handle_ping(user_id, source_ref)
    if lowered == "/version":
        return handle_version(user_id, source_ref)
    if lowered == "/help":
        route = _log_command_route(user_id, source_ref)
        if not route.allowed:
            return _brevity_text(user_id, short="Маршрут команд недоступен.", normal=COMMAND_ROUTE_UNAVAILABLE_RU)
        return handle_help(user_id)
    if lowered == "/status":
        route = _log_command_route(user_id, source_ref)
        if not route.allowed:
            return "Р В Р’В Р вЂ™Р’В Р В Р Р‹Р РЋРІвЂћСћР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В°Р В Р’В Р В Р вЂ№Р В Р’В Р Р†Р вЂљРЎв„ўР В Р’В Р В Р вЂ№Р В Р вЂ Р Р†Р вЂљРЎв„ўР вЂ™Р’В¬Р В Р’В Р В Р вЂ№Р В Р’В Р Р†Р вЂљРЎв„ўР В Р’В Р В Р вЂ№Р В Р Р‹Р Р†Р вЂљРЎС™Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р РЋРІвЂћСћ Р В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРЎСљР В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРЎС›Р В Р’В Р вЂ™Р’В Р В Р Р‹Р вЂ™Р’ВР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В°Р В Р’В Р вЂ™Р’В Р В Р’В Р Р†Р вЂљР’В¦Р В Р’В Р вЂ™Р’В Р В РЎС›Р Р†Р вЂљР’ВР В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р Р†РІР‚С›РІР‚вЂњ Р В Р’В Р В Р вЂ№Р В Р’В Р РЋРІР‚СљР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’ВµР В Р’В Р вЂ™Р’В Р В Р вЂ Р Р†Р вЂљРЎвЂєР Р†Р вЂљРІР‚СљР В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р В Р вЂ№Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В°Р В Р’В Р В Р вЂ№Р В Р’В Р РЋРІР‚Сљ Р В Р’В Р вЂ™Р’В Р В Р’В Р Р†Р вЂљР’В¦Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’ВµР В Р’В Р вЂ™Р’В Р В РЎС›Р Р†Р вЂљР’ВР В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРЎС›Р В Р’В Р В Р вЂ№Р В Р’В Р РЋРІР‚СљР В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р РЋРІвЂћСћР В Р’В Р В Р вЂ№Р В Р Р‹Р Р†Р вЂљРЎС™Р В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРІР‚СњР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’ВµР В Р’В Р вЂ™Р’В Р В Р’В Р Р†Р вЂљР’В¦. Р В Р’В Р вЂ™Р’В Р В Р Р‹Р РЋРЎСџР В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРЎС›Р В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРІР‚СњР В Р’В Р В Р вЂ№Р В Р’В Р Р†Р вЂљРЎв„ўР В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРЎС›Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В±Р В Р’В Р В Р вЂ№Р В Р Р‹Р Р†Р вЂљРЎС™Р В Р’В Р вЂ™Р’В Р В Р вЂ Р Р†Р вЂљРЎвЂєР Р†Р вЂљРІР‚СљР В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р РЋРІвЂћСћР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’Вµ Р В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРІР‚СњР В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРЎС›Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В·Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В¶Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’Вµ."
        return handle_status(user_id)
    if lowered == "/mode":
        route = _log_command_route(user_id, source_ref)
        if not route.allowed:
            return COMMAND_ROUTE_UNAVAILABLE_RU
        return handle_mode(user_id)
    if lowered == "/voice status":
        return handle_voice_status(user_id)
    if lowered == "/voice on":
        return handle_voice_set(user_id, True, source_ref=source_ref)
    if lowered == "/voice off":
        return handle_voice_set(user_id, False, source_ref=source_ref)
    if lowered.startswith("/voice"):
        return USAGE_VOICE
    if lowered == "/prefs":
        return handle_prefs_status(user_id)
    if lowered.startswith("/prefs "):
        tail = normalized[len("/prefs ") :].strip()
        parts = tail.split()
        if len(parts) == 2:
            return handle_prefs_set(user_id, parts[0], parts[1], source_ref=source_ref)
        return USAGE_PREFS
    if lowered.startswith("/mode "):
        return "Пока доступен только просмотр: /mode"
    if lowered == "/plan list":
        route = _log_command_route(user_id, source_ref)
        if not route.allowed:
            return "Р В Р’В Р вЂ™Р’В Р В Р Р‹Р РЋРІвЂћСћР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В°Р В Р’В Р В Р вЂ№Р В Р’В Р Р†Р вЂљРЎв„ўР В Р’В Р В Р вЂ№Р В Р вЂ Р Р†Р вЂљРЎв„ўР вЂ™Р’В¬Р В Р’В Р В Р вЂ№Р В Р’В Р Р†Р вЂљРЎв„ўР В Р’В Р В Р вЂ№Р В Р Р‹Р Р†Р вЂљРЎС™Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р РЋРІвЂћСћ Р В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРЎСљР В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРЎС›Р В Р’В Р вЂ™Р’В Р В Р Р‹Р вЂ™Р’ВР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В°Р В Р’В Р вЂ™Р’В Р В Р’В Р Р†Р вЂљР’В¦Р В Р’В Р вЂ™Р’В Р В РЎС›Р Р†Р вЂљР’ВР В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р Р†РІР‚С›РІР‚вЂњ Р В Р’В Р В Р вЂ№Р В Р’В Р РЋРІР‚СљР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’ВµР В Р’В Р вЂ™Р’В Р В Р вЂ Р Р†Р вЂљРЎвЂєР Р†Р вЂљРІР‚СљР В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р В Р вЂ№Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В°Р В Р’В Р В Р вЂ№Р В Р’В Р РЋРІР‚Сљ Р В Р’В Р вЂ™Р’В Р В Р’В Р Р†Р вЂљР’В¦Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’ВµР В Р’В Р вЂ™Р’В Р В РЎС›Р Р†Р вЂљР’ВР В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРЎС›Р В Р’В Р В Р вЂ№Р В Р’В Р РЋРІР‚СљР В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р РЋРІвЂћСћР В Р’В Р В Р вЂ№Р В Р Р‹Р Р†Р вЂљРЎС™Р В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРІР‚СњР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’ВµР В Р’В Р вЂ™Р’В Р В Р’В Р Р†Р вЂљР’В¦. Р В Р’В Р вЂ™Р’В Р В Р Р‹Р РЋРЎСџР В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРЎС›Р В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРІР‚СњР В Р’В Р В Р вЂ№Р В Р’В Р Р†Р вЂљРЎв„ўР В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРЎС›Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В±Р В Р’В Р В Р вЂ№Р В Р Р‹Р Р†Р вЂљРЎС™Р В Р’В Р вЂ™Р’В Р В Р вЂ Р Р†Р вЂљРЎвЂєР Р†Р вЂљРІР‚СљР В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р РЋРІвЂћСћР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’Вµ Р В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРІР‚СњР В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРЎС›Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В·Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В¶Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’Вµ."
        return handle_plan_list(user_id)
    if lowered.startswith("/plan done "):
        route = _log_command_route(user_id, source_ref)
        if not route.allowed:
            return COMMAND_ROUTE_UNAVAILABLE_RU
        event_id, error_text = _parse_plan_command_id(normalized, "/plan done ", USAGE_PLAN_DONE)
        if error_text:
            return error_text
        return handle_plan_done(user_id, int(event_id))
    if lowered == "/plan done":
        return USAGE_PLAN_DONE
    if lowered.startswith("/plan delete "):
        route = _log_command_route(user_id, source_ref)
        if not route.allowed:
            return COMMAND_ROUTE_UNAVAILABLE_RU
        event_id, error_text = _parse_plan_command_id(normalized, "/plan delete ", USAGE_PLAN_DELETE)
        if error_text:
            return error_text
        return handle_plan_delete(user_id, int(event_id))
    if lowered == "/plan delete":
        return USAGE_PLAN_DELETE
    if lowered.startswith("/plan add "):
        route = _log_command_route(user_id, source_ref)
        if not route.allowed:
            return "Р В Р’В Р вЂ™Р’В Р В Р Р‹Р РЋРІвЂћСћР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В°Р В Р’В Р В Р вЂ№Р В Р’В Р Р†Р вЂљРЎв„ўР В Р’В Р В Р вЂ№Р В Р вЂ Р Р†Р вЂљРЎв„ўР вЂ™Р’В¬Р В Р’В Р В Р вЂ№Р В Р’В Р Р†Р вЂљРЎв„ўР В Р’В Р В Р вЂ№Р В Р Р‹Р Р†Р вЂљРЎС™Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р РЋРІвЂћСћ Р В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРЎСљР В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРЎС›Р В Р’В Р вЂ™Р’В Р В Р Р‹Р вЂ™Р’ВР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В°Р В Р’В Р вЂ™Р’В Р В Р’В Р Р†Р вЂљР’В¦Р В Р’В Р вЂ™Р’В Р В РЎС›Р Р†Р вЂљР’ВР В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р Р†РІР‚С›РІР‚вЂњ Р В Р’В Р В Р вЂ№Р В Р’В Р РЋРІР‚СљР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’ВµР В Р’В Р вЂ™Р’В Р В Р вЂ Р Р†Р вЂљРЎвЂєР Р†Р вЂљРІР‚СљР В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р В Р вЂ№Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В°Р В Р’В Р В Р вЂ№Р В Р’В Р РЋРІР‚Сљ Р В Р’В Р вЂ™Р’В Р В Р’В Р Р†Р вЂљР’В¦Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’ВµР В Р’В Р вЂ™Р’В Р В РЎС›Р Р†Р вЂљР’ВР В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРЎС›Р В Р’В Р В Р вЂ№Р В Р’В Р РЋРІР‚СљР В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р РЋРІвЂћСћР В Р’В Р В Р вЂ№Р В Р Р‹Р Р†Р вЂљРЎС™Р В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРІР‚СњР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’ВµР В Р’В Р вЂ™Р’В Р В Р’В Р Р†Р вЂљР’В¦. Р В Р’В Р вЂ™Р’В Р В Р Р‹Р РЋРЎСџР В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРЎС›Р В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРІР‚СњР В Р’В Р В Р вЂ№Р В Р’В Р Р†Р вЂљРЎв„ўР В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРЎС›Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В±Р В Р’В Р В Р вЂ№Р В Р Р‹Р Р†Р вЂљРЎС™Р В Р’В Р вЂ™Р’В Р В Р вЂ Р Р†Р вЂљРЎвЂєР Р†Р вЂљРІР‚СљР В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р РЋРІвЂћСћР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’Вµ Р В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРІР‚СњР В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРЎС›Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В·Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В¶Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’Вµ."
        title = normalized[len("/plan add ") :].strip()
        if not title:
            return fix_mojibake("Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р Р†Р вЂљРІвЂћСћР В РІР‚в„ўР вЂ™Р’ВР В Р’В Р вЂ™Р’В Р В Р’В Р В РІР‚в„–Р В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРЎС™Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р Р†Р вЂљРЎСљР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р РЋРЎвЂєР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р Р†Р вЂљРІвЂћСћР В РІР‚в„ўР вЂ™Р’В»Р В Р’В Р вЂ™Р’В Р В Р’В Р В РІР‚в„–Р В Р’В Р вЂ™Р’В Р В Р’В Р Р†Р вЂљР’В°Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р Р†Р вЂљРІвЂћСћР В РІР‚в„ўР вЂ™Р’В·Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р РЋРЎвЂєР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р вЂ™Р’В Р В Р вЂ Р В РІР‚С™Р вЂ™Р’В Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р Р†Р вЂљРІвЂћСћР В РІР‚в„ўР вЂ™Р’В°Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р вЂ™Р’В Р В Р вЂ Р В РІР‚С™Р вЂ™Р’В¦Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р вЂ™Р’ВР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р Р†Р вЂљРІвЂћСћР В РІР‚в„ўР вЂ™Р’Вµ: /plan add <title>")
        return handle_plan_add(user_id, title, source_ref=source_ref)
    if lowered == "/plan add":
        return fix_mojibake("Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р Р†Р вЂљРІвЂћСћР В РІР‚в„ўР вЂ™Р’ВР В Р’В Р вЂ™Р’В Р В Р’В Р В РІР‚в„–Р В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРЎС™Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р Р†Р вЂљРЎСљР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р РЋРЎвЂєР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р Р†Р вЂљРІвЂћСћР В РІР‚в„ўР вЂ™Р’В»Р В Р’В Р вЂ™Р’В Р В Р’В Р В РІР‚в„–Р В Р’В Р вЂ™Р’В Р В Р’В Р Р†Р вЂљР’В°Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р Р†Р вЂљРІвЂћСћР В РІР‚в„ўР вЂ™Р’В·Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р РЋРЎвЂєР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р вЂ™Р’В Р В Р вЂ Р В РІР‚С™Р вЂ™Р’В Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р Р†Р вЂљРІвЂћСћР В РІР‚в„ўР вЂ™Р’В°Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р вЂ™Р’В Р В Р вЂ Р В РІР‚С™Р вЂ™Р’В¦Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р вЂ™Р’ВР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В Р В Р’В Р Р†Р вЂљРІвЂћСћР В РІР‚в„ўР вЂ™Р’Вµ: /plan add <title>")
    if lowered.startswith("/plan"):
        return "Использование: /plan add <title> | /plan list | /plan done <id> | /plan delete <id>"
    if lowered == "/hb now":
        route = _log_command_route(user_id, source_ref)
        if not route.allowed:
            return COMMAND_ROUTE_UNAVAILABLE_RU
        return handle_hb_now()
    if lowered == "/hb status":
        route = _log_command_route(user_id, source_ref)
        if not route.allowed:
            return COMMAND_ROUTE_UNAVAILABLE_RU
        return handle_hb_status()
    if lowered.startswith("/hb interval "):
        route = _log_command_route(user_id, source_ref)
        if not route.allowed:
            return COMMAND_ROUTE_UNAVAILABLE_RU
        minutes_raw = normalized[len("/hb interval ") :].strip()
        if not minutes_raw:
            return USAGE_HB
        return handle_hb_interval(minutes_raw)
    if lowered == "/hb interval":
        return USAGE_HB
    if lowered == "/hb on":
        route = _log_command_route(user_id, source_ref)
        if not route.allowed:
            return COMMAND_ROUTE_UNAVAILABLE_RU
        return handle_hb_toggle(True)
    if lowered == "/hb off":
        route = _log_command_route(user_id, source_ref)
        if not route.allowed:
            return COMMAND_ROUTE_UNAVAILABLE_RU
        return handle_hb_toggle(False)
    if lowered.startswith("/hb"):
        return USAGE_HB
    if lowered == "/digest now":
        route = _log_command_route(user_id, source_ref)
        if not route.allowed:
            return COMMAND_ROUTE_UNAVAILABLE_RU
        return handle_digest_now()
    if lowered == "/digest preview":
        route = _log_command_route(user_id, source_ref)
        if not route.allowed:
            return COMMAND_ROUTE_UNAVAILABLE_RU
        return handle_digest_preview()
    if lowered == "/digest status":
        route = _log_command_route(user_id, source_ref)
        if not route.allowed:
            return COMMAND_ROUTE_UNAVAILABLE_RU
        return handle_digest_status_for_user(user_id)
    if lowered == "/digest target here":
        route = _log_command_route(user_id, source_ref)
        if not route.allowed:
            return COMMAND_ROUTE_UNAVAILABLE_RU
        return handle_digest_target_here(user_id, source_ref)
    if lowered == "/digest target show":
        route = _log_command_route(user_id, source_ref)
        if not route.allowed:
            return COMMAND_ROUTE_UNAVAILABLE_RU
        return handle_digest_target_show(user_id)
    if lowered == "/digest target on":
        route = _log_command_route(user_id, source_ref)
        if not route.allowed:
            return COMMAND_ROUTE_UNAVAILABLE_RU
        return handle_digest_target_toggle(user_id, True)
    if lowered == "/digest target off":
        route = _log_command_route(user_id, source_ref)
        if not route.allowed:
            return COMMAND_ROUTE_UNAVAILABLE_RU
        return handle_digest_target_toggle(user_id, False)
    if lowered == "/digest target clear":
        route = _log_command_route(user_id, source_ref)
        if not route.allowed:
            return COMMAND_ROUTE_UNAVAILABLE_RU
        return handle_digest_target_clear(user_id)
    if lowered == "/digest target test":
        route = _log_command_route(user_id, source_ref)
        if not route.allowed:
            return COMMAND_ROUTE_UNAVAILABLE_RU
        return handle_digest_target_test(user_id)
    if lowered.startswith("/digest target"):
        return USAGE_DIGEST_TARGET
    if lowered == "/digest on":
        route = _log_command_route(user_id, source_ref)
        if not route.allowed:
            return COMMAND_ROUTE_UNAVAILABLE_RU
        return handle_digest_toggle(True)
    if lowered == "/digest off":
        route = _log_command_route(user_id, source_ref)
        if not route.allowed:
            return COMMAND_ROUTE_UNAVAILABLE_RU
        return handle_digest_toggle(False)
    if lowered.startswith("/digest time "):
        route = _log_command_route(user_id, source_ref)
        if not route.allowed:
            return COMMAND_ROUTE_UNAVAILABLE_RU
        time_value = normalized[len("/digest time ") :].strip()
        if not time_value:
            return USAGE_DIGEST
        return handle_digest_time(time_value)
    if lowered == "/digest time":
        return USAGE_DIGEST
    if lowered.startswith("/digest"):
        return USAGE_DIGEST
    if lowered == "/cron list":
        route = _log_command_route(user_id, source_ref)
        if not route.allowed:
            return COMMAND_ROUTE_UNAVAILABLE_RU
        return handle_cron_list()
    if lowered.startswith("/cron run "):
        route = _log_command_route(user_id, source_ref)
        if not route.allowed:
            return COMMAND_ROUTE_UNAVAILABLE_RU
        job_name = normalized[len("/cron run ") :].strip()
        if not job_name:
            return USAGE_CRON
        return handle_cron_run(job_name, user_id=user_id)
    if lowered == "/cron run":
        return USAGE_CRON
    if lowered == "/cron sync":
        route = _log_command_route(user_id, source_ref)
        if not route.allowed:
            return COMMAND_ROUTE_UNAVAILABLE_RU
        return handle_cron_sync()
    if lowered.startswith("/cron"):
        return USAGE_CRON
    return None


def dispatch_openclaw_bridge_command(
    text: str,
    *,
    user_id: int,
    source_ref: str | None = None,
) -> str | None:
    """Backward-compatible alias for bridge dispatch."""
    return dispatch_command(text, user_id=user_id, source_ref=source_ref)


def dispatch_command_response(
    text: str,
    *,
    user_id: int,
    source_ref: str | None = None,
    request_id: str | None = None,
) -> OpenClawBridgeResponse:
    source_key = str(source_ref or "openclaw:command")
    normalized_text = " ".join((text or "").strip().split()).lower()
    duplicate_key = f"cmdresp:{user_id}:{source_key}:{normalized_text}"
    cached = _duplicate_guard_get(duplicate_key)
    if isinstance(cached, dict):
        payload = normalize_bridge_response(cached)
        payload["meta"] = dict(payload.get("meta") or {})
        payload["meta"]["duplicate_skipped"] = True
        _log_bridge_event(
            route="command",
            user_id=user_id,
            source_ref=source_key,
            handler="dispatch_command_response:duplicate_skip",
            ok=bool(payload.get("ok")),
            latency_ms=0,
            duplicate_skipped=True,
            error_code=str(payload.get("error_code") or ""),
            request_id=request_id,
        )
        return payload
    result = dispatch_command(
        text,
        user_id=user_id,
        source_ref=source_ref,
        request_id=request_id,
    )
    normalized = normalize_bridge_response(result)
    text_value = str(normalized.get("text") or "")
    if result is None:
        normalized["ok"] = False
        normalized["error_code"] = "ignored"
        normalized["meta"] = dict(normalized.get("meta") or {})
        normalized["meta"]["duplicate_skipped"] = False
        _duplicate_guard_put(duplicate_key, dict(normalized))
        return normalized
    if text_value.startswith("Использование:"):
        normalized["ok"] = False
        normalized["error_code"] = "invalid_usage"
    elif text_value == "ID должен быть числом.":
        normalized["ok"] = False
        normalized["error_code"] = "invalid_id"
    elif text_value.startswith("Не найдено:"):
        normalized["ok"] = False
        normalized["error_code"] = "not_found"
    elif text_value == COMMAND_ROUTE_UNAVAILABLE_RU:
        normalized["ok"] = False
        normalized["error_code"] = "route_unavailable"
    normalized["meta"] = dict(normalized.get("meta") or {})
    normalized["meta"]["duplicate_skipped"] = False
    _duplicate_guard_put(duplicate_key, dict(normalized))
    return normalized


TRANSCRIPT_WARNING = (
    "Р В Р’В Р вЂ™Р’В Р В Р Р‹Р РЋРЎСџР В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРЎС›Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В»Р В Р’В Р В Р вЂ№Р В Р Р‹Р Р†Р вЂљРЎС™Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р В Р вЂ№Р В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљР’ВР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В» Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р РЋРІвЂћСћР В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРЎС›Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В»Р В Р’В Р В Р вЂ№Р В Р’В Р В РІР‚В°Р В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРЎСљР В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРЎС› Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В°Р В Р’В Р вЂ™Р’В Р В Р’В Р Р†Р вЂљР’В Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р РЋРІвЂћСћР В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРЎС›-Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р РЋРІвЂћСћР В Р’В Р В Р вЂ№Р В Р’В Р Р†Р вЂљРЎв„ўР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В°Р В Р’В Р вЂ™Р’В Р В Р’В Р Р†Р вЂљР’В¦Р В Р’В Р В Р вЂ№Р В Р’В Р РЋРІР‚СљР В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРЎСљР В Р’В Р В Р вЂ№Р В Р’В Р Р†Р вЂљРЎв„ўР В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљР’ВР В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРІР‚СњР В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р РЋРІвЂћСћ Telegram (Р В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРЎС›Р В Р’В Р вЂ™Р’В Р В Р’В Р Р†Р вЂљР’В¦ Р В Р’В Р вЂ™Р’В Р В Р Р‹Р вЂ™Р’ВР В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРЎС›Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В¶Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’ВµР В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р РЋРІвЂћСћ Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В±Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р Р†РІР‚С›РІР‚вЂњР В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р РЋРІвЂћСћР В Р’В Р В Р вЂ№Р В Р’В Р В РІР‚В° Р В Р’В Р вЂ™Р’В Р В Р’В Р Р†Р вЂљР’В¦Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’ВµР В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р РЋРІвЂћСћР В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРЎС›Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р В Р вЂ№Р В Р’В Р вЂ™Р’В Р В Р’В Р Р†Р вЂљР’В¦Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р Р†РІР‚С›РІР‚вЂњР В Р’В Р вЂ™Р’В Р В Р Р‹Р вЂ™Р’В). "
    "Р В Р’В Р вЂ™Р’В Р В Р вЂ Р В РІР‚С™Р РЋРІР‚СњР В Р’В Р В Р вЂ№Р В Р Р‹Р Р†Р вЂљРЎС™Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р В Р вЂ№Р В Р’В Р В Р вЂ№Р В Р вЂ Р Р†Р вЂљРЎв„ўР вЂ™Р’В¬Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’Вµ Р В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРЎС›Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р РЋРІвЂћСћР В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРІР‚СњР В Р’В Р В Р вЂ№Р В Р’В Р Р†Р вЂљРЎв„ўР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В°Р В Р’В Р вЂ™Р’В Р В Р’В Р Р†Р вЂљР’В Р В Р’В Р В Р вЂ№Р В Р’В Р В РІР‚В° Р В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРЎС›Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В±Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р Р†РІР‚С›РІР‚вЂњР В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р В Р вЂ№Р В Р’В Р вЂ™Р’В Р В Р’В Р Р†Р вЂљР’В¦Р В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРЎС›Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’Вµ Р В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРІР‚СљР В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРЎС›Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В»Р В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРЎС›Р В Р’В Р В Р вЂ№Р В Р’В Р РЋРІР‚СљР В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРЎС›Р В Р’В Р вЂ™Р’В Р В Р’В Р Р†Р вЂљР’В Р В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРЎС›Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’Вµ Р В Р’В Р В Р вЂ№Р В Р’В Р РЋРІР‚СљР В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРЎС›Р В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРЎС›Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В±Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р вЂ™Р’В°Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’ВµР В Р’В Р вЂ™Р’В Р В Р’В Р Р†Р вЂљР’В¦Р В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљР’ВР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’Вµ - Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р РЋРІвЂћСћР В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРЎС›Р В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРІР‚СљР В Р’В Р вЂ™Р’В Р В РЎС›Р Р†Р вЂљР’ВР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В° Р В Р’В Р В Р вЂ№Р В Р’В Р Р†Р вЂљРЎв„ўР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В°Р В Р’В Р В Р вЂ№Р В Р’В Р РЋРІР‚СљР В Р’В Р В Р вЂ№Р В Р вЂ Р Р†Р вЂљРЎв„ўР вЂ™Р’В¬Р В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљР’ВР В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р РЋРІР‚С”Р В Р’В Р В Р вЂ№Р В Р’В Р Р†Р вЂљРЎв„ўР В Р’В Р В Р вЂ№Р В Р Р‹Р Р†Р вЂљРЎС™Р В Р’В Р В Р вЂ№Р В Р’В Р Р†Р вЂљРІвЂћвЂ“ Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р РЋРІвЂћСћР В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРЎС›Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р В Р вЂ№Р В Р’В Р вЂ™Р’В Р В Р’В Р Р†Р вЂљР’В¦Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’ВµР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’Вµ."
)
STT_FAIL_FALLBACK_RU = "Р В Р’В Р вЂ™Р’В Р В Р Р‹Р РЋРЎв„ўР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’Вµ Р В Р’В Р В Р вЂ№Р В Р Р‹Р Р†Р вЂљРЎС™Р В Р’В Р вЂ™Р’В Р В РЎС›Р Р†Р вЂљР’ВР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В°Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В»Р В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРЎС›Р В Р’В Р В Р вЂ№Р В Р’В Р РЋРІР‚СљР В Р’В Р В Р вЂ№Р В Р’В Р В РІР‚В° Р В Р’В Р В Р вЂ№Р В Р’В Р Р†Р вЂљРЎв„ўР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В°Р В Р’В Р В Р вЂ№Р В Р’В Р РЋРІР‚СљР В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРІР‚СњР В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРЎС›Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В·Р В Р’В Р вЂ™Р’В Р В Р’В Р Р†Р вЂљР’В¦Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В°Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р РЋРІвЂћСћР В Р’В Р В Р вЂ№Р В Р’В Р В РІР‚В° Р В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРІР‚СљР В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРЎС›Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В»Р В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРЎС›Р В Р’В Р В Р вЂ№Р В Р’В Р РЋРІР‚СљР В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРЎС›Р В Р’В Р вЂ™Р’В Р В Р’В Р Р†Р вЂљР’В Р В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРЎС›Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’Вµ. Р В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРЎвЂќР В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р РЋРІвЂћСћР В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРІР‚СњР В Р’В Р В Р вЂ№Р В Р’В Р Р†Р вЂљРЎв„ўР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В°Р В Р’В Р вЂ™Р’В Р В Р’В Р Р†Р вЂљР’В Р В Р’В Р В Р вЂ№Р В Р’В Р В РІР‚В° Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’ВµР В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р вЂ™Р’В°Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’Вµ Р В Р’В Р В Р вЂ№Р В Р’В Р Р†Р вЂљРЎв„ўР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В°Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В· Р В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРЎС›Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В±Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р Р†РІР‚С›РІР‚вЂњР В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р В Р вЂ№Р В Р’В Р вЂ™Р’В Р В Р’В Р Р†Р вЂљР’В¦Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р Р†РІР‚С›РІР‚вЂњР В Р’В Р вЂ™Р’В Р В Р Р‹Р вЂ™Р’В Р В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРІР‚СљР В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРЎС›Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В»Р В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРЎС›Р В Р’В Р В Р вЂ№Р В Р’В Р РЋРІР‚СљР В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРЎС›Р В Р’В Р вЂ™Р’В Р В Р’В Р Р†Р вЂљР’В Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р Р†РІР‚С›РІР‚вЂњР В Р’В Р вЂ™Р’В Р В Р Р‹Р вЂ™Р’В Р В Р’В Р В Р вЂ№Р В Р’В Р РЋРІР‚СљР В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРЎС›Р В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРЎС›Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В±Р В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р вЂ™Р’В°Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’ВµР В Р’В Р вЂ™Р’В Р В Р’В Р Р†Р вЂљР’В¦Р В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљР’ВР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’ВµР В Р’В Р вЂ™Р’В Р В Р Р‹Р вЂ™Р’В."
INTERNAL_ERROR_RU = "Р В Р’В Р вЂ™Р’В Р В Р вЂ Р В РІР‚С™Р Р†РІР‚С›РЎС›Р В Р’В Р В Р вЂ№Р В Р’В Р Р†Р вЂљРЎв„ўР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’ВµР В Р’В Р вЂ™Р’В Р В Р Р‹Р вЂ™Р’ВР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’ВµР В Р’В Р вЂ™Р’В Р В Р’В Р Р†Р вЂљР’В¦Р В Р’В Р вЂ™Р’В Р В Р’В Р Р†Р вЂљР’В¦Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В°Р В Р’В Р В Р вЂ№Р В Р’В Р В Р РЏ Р В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРЎС›Р В Р’В Р В Р вЂ№Р В Р вЂ Р Р†Р вЂљРЎв„ўР вЂ™Р’В¬Р В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљР’ВР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В±Р В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРЎСљР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В°. Р В Р’В Р вЂ™Р’В Р В Р Р‹Р РЋРЎСџР В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРЎС›Р В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРІР‚СњР В Р’В Р В Р вЂ№Р В Р’В Р Р†Р вЂљРЎв„ўР В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРЎС›Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В±Р В Р’В Р В Р вЂ№Р В Р Р‹Р Р†Р вЂљРЎС™Р В Р’В Р вЂ™Р’В Р В Р вЂ Р Р†Р вЂљРЎвЂєР Р†Р вЂљРІР‚СљР В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р РЋРІвЂћСћР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’Вµ Р В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРІР‚СњР В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРЎС›Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В·Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В¶Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’Вµ."
STT_DEFAULT_LANGUAGE = "ru"
STT_TUTOR_LANGUAGE = "en"
REASONING_UNAVAILABLE_RU = (
    "Р В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРЎвЂќР В Р’В Р В Р вЂ№Р В Р’В Р РЋРІР‚СљР В Р’В Р вЂ™Р’В Р В Р’В Р Р†Р вЂљР’В¦Р В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРЎС›Р В Р’В Р вЂ™Р’В Р В Р’В Р Р†Р вЂљР’В Р В Р’В Р вЂ™Р’В Р В Р’В Р Р†Р вЂљР’В¦Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В°Р В Р’В Р В Р вЂ№Р В Р’В Р В Р РЏ reasoning-Р В Р’В Р вЂ™Р’В Р В Р Р‹Р вЂ™Р’ВР В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРЎС›Р В Р’В Р вЂ™Р’В Р В РЎС›Р Р†Р вЂљР’ВР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’ВµР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В»Р В Р’В Р В Р вЂ№Р В Р’В Р В РІР‚В° Р В Р’В Р В Р вЂ№Р В Р’В Р РЋРІР‚СљР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’ВµР В Р’В Р вЂ™Р’В Р В Р вЂ Р Р†Р вЂљРЎвЂєР Р†Р вЂљРІР‚СљР В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р В Р вЂ№Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В°Р В Р’В Р В Р вЂ№Р В Р’В Р РЋРІР‚Сљ Р В Р’В Р вЂ™Р’В Р В Р’В Р Р†Р вЂљР’В¦Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’ВµР В Р’В Р вЂ™Р’В Р В РЎС›Р Р†Р вЂљР’ВР В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРЎС›Р В Р’В Р В Р вЂ№Р В Р’В Р РЋРІР‚СљР В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р РЋРІвЂћСћР В Р’В Р В Р вЂ№Р В Р Р‹Р Р†Р вЂљРЎС™Р В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРІР‚СњР В Р’В Р вЂ™Р’В Р В Р’В Р Р†Р вЂљР’В¦Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В°. Р В Р’В Р вЂ™Р’В Р В Р Р‹Р РЋРЎСџР В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРЎС›Р В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРІР‚СњР В Р’В Р В Р вЂ№Р В Р’В Р Р†Р вЂљРЎв„ўР В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРЎС›Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В±Р В Р’В Р В Р вЂ№Р В Р Р‹Р Р†Р вЂљРЎС™Р В Р’В Р вЂ™Р’В Р В Р вЂ Р Р†Р вЂљРЎвЂєР Р†Р вЂљРІР‚СљР В Р’В Р В Р вЂ№Р В Р вЂ Р В РІР‚С™Р РЋРІвЂћСћР В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’Вµ Р В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРІР‚СњР В Р’В Р вЂ™Р’В Р В Р Р‹Р Р†Р вЂљРЎС›Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В·Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’В¶Р В Р’В Р вЂ™Р’В Р В РІР‚в„ўР вЂ™Р’Вµ."
)


def looks_like_auto_transcript(text: str | None) -> bool:
    normalized = (text or "").strip().lower()
    return normalized.startswith("transcript:") or normalized.startswith("transcription:")


def _guess_media_intent(mime_type: str | None) -> str:
    lowered = (mime_type or "").lower()
    if "ogg" in lowered or "opus" in lowered:
        return "sendVoice"
    return "sendAudio"


def _is_audio_document_payload(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    mime_type = str(value.get("mime_type") or value.get("mimeType") or "").lower()
    if mime_type.startswith("audio/"):
        return True
    file_name = str(value.get("file_name") or value.get("fileName") or "").lower()
    return file_name.endswith((".ogg", ".opus", ".m4a", ".mp3", ".wav"))


def _coerce_audio_bytes(value: Any) -> bytes | None:
    if isinstance(value, bytes):
        return value
    if isinstance(value, bytearray):
        return bytes(value)
    return None


def _coerce_audio_path(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _extract_media_bytes_and_path(container: dict[str, Any] | None) -> tuple[bytes | None, str | None]:
    if not isinstance(container, dict):
        return None, None
    media_bytes = _coerce_audio_bytes(
        container.get("audio_bytes")
        or container.get("media_bytes")
        or container.get("file_bytes")
        or container.get("bytes")
        or container.get("data")
    )
    media_path = _coerce_audio_path(
        container.get("audio_path")
        or container.get("media_path")
        or container.get("file_path")
        or container.get("path")
    )
    return media_bytes, media_path


def _normalize_media_downloader_result(value: Any) -> tuple[bytes | None, str | None]:
    if value is None:
        return None, None
    if isinstance(value, (bytes, bytearray)):
        return _coerce_audio_bytes(value), None
    if isinstance(value, str):
        return None, _coerce_audio_path(value)
    if isinstance(value, (tuple, list)) and len(value) == 2:
        left, right = value[0], value[1]
        left_bytes = _coerce_audio_bytes(left)
        right_bytes = _coerce_audio_bytes(right)
        if left_bytes is not None:
            return left_bytes, _coerce_audio_path(right)
        if right_bytes is not None:
            return right_bytes, _coerce_audio_path(left)
        return None, _coerce_audio_path(left) or _coerce_audio_path(right)
    if isinstance(value, dict):
        return _extract_media_bytes_and_path(value)
    return None, None


def _call_message_media_downloader(
    message: dict[str, Any],
    *,
    media_kind: str,
    file_id: str,
) -> tuple[bytes | None, str | None, bool, bool, str | None]:
    downloader = (
        message.get("telegram_media_downloader")
        or message.get("media_downloader")
        or message.get("download_media")
    )
    if not callable(downloader):
        return None, None, False, False, "downloader_missing"
    try:
        result = downloader(file_id=file_id, media_kind=media_kind, message=message)
    except TypeError:
        try:
            result = downloader(file_id, media_kind, message)
        except Exception as exc:  # pragma: no cover - defensive fallback
            return None, None, True, False, f"downloader_exception:{_sanitize_text_for_logs(exc)}"
    except Exception as exc:
        return None, None, True, False, f"downloader_exception:{_sanitize_text_for_logs(exc)}"
    media_bytes, media_path = _normalize_media_downloader_result(result)
    ok = bool(media_bytes is not None or media_path)
    return media_bytes, media_path, True, ok, "" if ok else "downloader_empty"


def _log_telegram_voice_path(event: str, payload: dict[str, Any]) -> None:
    fallback_reason = _normalize_voice_fallback_reason(payload.get("fallbackReason") or payload.get("fallback_reason"))
    final_input_source = str(
        payload.get("finalInputSource")
        or payload.get("final_input_source")
        or payload.get("sttSource")
        or payload.get("stt_source")
        or ""
    )
    if final_input_source not in {"voice_file", "audio_file", "document_file", "transcript"}:
        final_input_source = ""
    response_mode = _voice_response_mode_from_payload(payload)
    final_outcome = _voice_final_outcome_from_payload(
        {
            **payload,
            "fallbackReason": fallback_reason,
            "finalInputSource": final_input_source,
            "responseMode": response_mode,
        }
    )
    downloader_name = str(payload.get("downloaderName") or payload.get("downloader_name") or "")
    downloader_path = str(payload.get("downloaderPath") or payload.get("downloader_path") or "")
    message_kind = str(payload.get("messageKind") or payload.get("message_kind") or "") or _voice_message_kind_from_flags(payload)
    if event == "telegram_stt_source_select":
        if final_input_source == "voice_file":
            _obs_increment_counter("telegram_voice_source.voice_file")
        if final_input_source == "transcript":
            _obs_increment_counter("telegram_voice_source.transcript")
    if event == "telegram_voice_ingest" and fallback_reason in {
        "voice_download_failed",
        "empty_transcript_voice_note",
        "transcript_only_auto",
    }:
        _obs_increment_counter(f"telegram_voice_fallback.{fallback_reason}")
    logger.info(
        "%s",
        json.dumps(
            {
                "event": event,
                "requestId": str(payload.get("requestId") or payload.get("request_id") or ""),
                "userIdHash": str(payload.get("userIdHash") or payload.get("user_id_hash") or ""),
                "messageKind": message_kind,
                "hasVoice": bool(payload.get("hasVoice")),
                "hasAudio": bool(payload.get("hasAudio")),
                "hasDocument": bool(payload.get("hasDocument")),
                "hasText": bool(payload.get("hasText")),
                "hasTranscript": bool(payload.get("hasTranscript")),
                "transcriptLen": int(payload.get("transcriptLen") or payload.get("transcript_len") or payload.get("sttResultLen") or 0),
                "transcriptLooksAuto": bool(payload.get("transcriptLooksAuto")),
                "voiceDuration": int(payload.get("voiceDuration") or 0) if payload.get("voiceDuration") is not None else None,
                "mimeType": str(payload.get("mimeType") or ""),
                "telegramFileIdPresent": bool(payload.get("telegramFileIdPresent") if payload.get("telegramFileIdPresent") is not None else payload.get("fileIdPresent")),
                "telegramFileUniqueIdPresent": bool(payload.get("telegramFileUniqueIdPresent") or payload.get("fileUniqueIdPresent")),
                "downloaderName": downloader_name,
                "downloaderPath": downloader_path,
                "downloadAttempted": bool(payload.get("downloadAttempted")),
                "downloadOk": bool(payload.get("downloadOk")),
                "downloadBytes": int(payload.get("downloadBytes") or 0),
                "downloadError": str(payload.get("downloadError") or ""),
                "mediaBytesPresent": bool(payload.get("mediaBytesPresent")),
                "mediaBytesLen": int(payload.get("mediaBytesLen") or 0),
                "mediaPathPresent": bool(payload.get("mediaPathPresent")),
                "mediaPathExists": payload.get("mediaPathExists") if payload.get("mediaPathExists") is not None else None,
                "mediaPathSize": int(payload.get("mediaPathSize") or 0) if payload.get("mediaPathSize") is not None else None,
                "mediaPathBase": str(payload.get("mediaPathBase") or ""),
                "sttAttempted": bool(payload.get("sttAttempted")),
                "sttOk": bool(payload.get("sttOk")),
                "sttSource": str(payload.get("sttSource") or payload.get("stt_source") or ""),
                "sttResultLen": int(payload.get("sttResultLen") or 0),
                "finalInputSource": final_input_source,
                "finalOutcome": final_outcome,
                "fallbackReason": fallback_reason,
                "responseMode": response_mode,
                "durationMs": int(payload.get("durationMs") or payload.get("duration_ms") or 0) if (payload.get("durationMs") is not None or payload.get("duration_ms") is not None) else None,
            },
            ensure_ascii=True,
            separators=(",", ":"),
        ),
    )


def _normalize_voice_payload(
    message: dict[str, Any],
) -> dict[str, Any]:
    transcript_text = str(message.get("transcript") or message.get("auto_transcript") or "")
    text = str(message.get("text") or message.get("content") or transcript_text or "")
    voice_obj = message.get("voice") if isinstance(message.get("voice"), dict) else None
    audio_obj = message.get("audio") if isinstance(message.get("audio"), dict) else None
    document_obj = message.get("document") if isinstance(message.get("document"), dict) else None
    has_voice = voice_obj is not None
    has_audio = audio_obj is not None
    has_document = document_obj is not None
    media_hints = bool(
        has_voice
        or has_audio
        or has_document
        or message.get("has_media")
        or message.get("media_present")
        or message.get("media_type")
    )

    top_audio_bytes = _coerce_audio_bytes(message.get("audio_bytes") or message.get("media_bytes") or message.get("file_bytes"))
    top_audio_path = _coerce_audio_path(message.get("audio_path") or message.get("media_path") or message.get("file_path"))
    source_type = ""
    selected_obj: dict[str, Any] | None = None
    selected_kind = ""
    malformed_selected_media = False
    for kind, candidate in (("voice", voice_obj), ("audio", audio_obj), ("document", document_obj)):
        if not isinstance(candidate, dict):
            continue
        if kind == "document" and not _is_audio_document_payload(candidate):
            continue
        selected_obj = candidate
        selected_kind = kind
        source_type = f"{kind}_file"
        break
    if not source_type:
        if has_voice:
            source_type = "voice_file"
        elif has_audio:
            source_type = "audio_file"
        elif has_document and _is_audio_document_payload(document_obj):
            source_type = "document_file"
        elif top_audio_bytes is not None or top_audio_path:
            source_type = "audio_file"

    nested_audio_bytes, nested_audio_path = _extract_media_bytes_and_path(selected_obj)
    audio_bytes = nested_audio_bytes if nested_audio_bytes is not None else top_audio_bytes
    audio_path = nested_audio_path or top_audio_path
    file_id = ""
    mime_type = ""
    voice_duration: int | None = None
    if isinstance(selected_obj, dict):
        file_id = str(selected_obj.get("file_id") or selected_obj.get("fileId") or "")
        file_unique_id = str(selected_obj.get("file_unique_id") or selected_obj.get("fileUniqueId") or "")
        mime_type = str(selected_obj.get("mime_type") or selected_obj.get("mimeType") or "")
        duration_raw = selected_obj.get("duration") or selected_obj.get("duration_seconds")
        if isinstance(duration_raw, (int, float)):
            voice_duration = int(duration_raw)
    else:
        file_unique_id = ""

    download_attempted = False
    download_ok = False
    download_bytes = len(audio_bytes) if isinstance(audio_bytes, bytes) else 0
    fallback_reason = ""
    download_error = ""
    downloader_name = ""
    downloader_path = ""
    for candidate_key in ("telegram_media_downloader", "media_downloader", "download_media"):
        if callable(message.get(candidate_key)):
            downloader_name = _safe_downloader_name(message.get(candidate_key))
            downloader_path = candidate_key
            break
    if source_type in {"voice_file", "audio_file", "document_file"} and audio_bytes is None and not audio_path and file_id:
        dl_bytes, dl_path, dl_attempted, dl_ok, dl_err = _call_message_media_downloader(
            message,
            media_kind=selected_kind or source_type.replace("_file", ""),
            file_id=file_id,
        )
        download_attempted = dl_attempted
        download_ok = dl_ok
        if dl_bytes is not None:
            audio_bytes = dl_bytes
        elif dl_path:
            audio_path = dl_path
        download_bytes = len(audio_bytes) if isinstance(audio_bytes, bytes) else 0
        if not dl_ok:
            if source_type == "voice_file":
                fallback_reason = "voice_download_failed" if dl_attempted else "voice_download_not_attempted"
            else:
                fallback_reason = "stt_error"
            if dl_err:
                download_error = dl_err
    elif source_type in {"voice_file", "audio_file", "document_file"} and audio_bytes is None and not audio_path and not file_id:
        malformed_selected_media = True
        fallback_reason = "unsupported_media_shape"

    if audio_bytes is not None:
        audio_path = None
        download_ok = download_ok or download_attempted or True
        download_bytes = len(audio_bytes)
    elif audio_path:
        download_ok = download_ok or download_attempted or False

    media_path_exists: bool | None = None
    media_path_size: int | None = None
    media_path_base = ""
    if audio_path:
        media_path_base = _safe_log_basename(audio_path)
        try:
            p = Path(audio_path)
            media_path_exists = p.exists() and p.is_file()
            if media_path_exists:
                media_path_size = int(p.stat().st_size)
        except Exception:
            media_path_exists = False
            media_path_size = None

    stt_source = source_type or ("transcript" if text else "")
    if not audio_bytes and not audio_path and not media_hints and text:
        stt_source = "transcript"
    if stt_source == "transcript" and not fallback_reason:
        fallback_reason = "transcript_only_no_media"
    if not text.strip() and not audio_bytes and not audio_path and not media_hints and not fallback_reason:
        fallback_reason = "no_voice_content"
    if malformed_selected_media and text.strip() and looks_like_auto_transcript(text):
        # transcript branch will normalize to transcript_only_auto only if no existing reason
        pass

    path_meta = {
        "requestId": str(message.get("request_id") or ""),
        "userIdHash": _hash_user_id_for_logs(message.get("user_id") or message.get("from_user_id") or ""),
        "messageKind": "voice" if has_voice else ("audio" if has_audio else ("document" if has_document else "transcript_only")),
        "hasVoice": has_voice,
        "hasAudio": has_audio,
        "hasDocument": has_document,
        "hasText": bool(text.strip()),
        "hasTranscript": bool(transcript_text.strip()),
        "transcriptLen": len(text.strip()),
        "transcriptLooksAuto": looks_like_auto_transcript(text),
        "voiceDuration": voice_duration,
        "mimeType": mime_type,
        "fileIdPresent": bool(file_id),
        "telegramFileIdPresent": bool(file_id),
        "telegramFileUniqueIdPresent": bool(file_unique_id),
        "fileUniqueIdPresent": bool(file_unique_id),
        "downloaderName": downloader_name,
        "downloaderPath": downloader_path,
        "downloadAttempted": download_attempted,
        "downloadOk": download_ok,
        "downloadBytes": download_bytes,
        "mediaBytesPresent": bool(isinstance(audio_bytes, bytes)),
        "mediaBytesLen": len(audio_bytes) if isinstance(audio_bytes, bytes) else 0,
        "mediaPathPresent": bool(audio_path),
        "mediaPathExists": media_path_exists,
        "mediaPathSize": media_path_size,
        "mediaPathBase": media_path_base,
        "sttAttempted": False,
        "sttOk": False,
        "sttSource": stt_source,
        "finalInputSource": stt_source if stt_source in {"voice_file", "audio_file", "document_file", "transcript"} else "",
        "sttResultLen": 0,
        "fallbackReason": _normalize_voice_fallback_reason(fallback_reason),
        "downloadError": download_error,
        "telegramVoiceNote": source_type == "voice_file",
        "telegramMediaKind": selected_kind or "",
    }
    return {
        "audio_bytes": audio_bytes,
        "audio_path": audio_path,
        "text": text,
        "media_declared": media_hints,
        "path_meta": path_meta,
    }


def _build_voice_response(
    *,
    handled: bool,
    text: str = "",
    status: str = "ok",
    error_code: str | None = None,
    audio_intent: str | None = None,
    audio_bytes: bytes | None = None,
    mime_type: str | None = None,
    diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    diag = diagnostics or {}
    return _build_bridge_response(
        ok=bool(handled and status == "ok"),
        text=text,
        audio_intent=audio_intent,
        audio_path=None,
        meta={"route": "voice"},
        error_code=error_code,
        handled=handled,
        status=status,
        audio_bytes=audio_bytes,
        mime_type=mime_type,
        diagnostics=diag,
    )


def _attach_route_diagnostics(
    diagnostics: dict[str, Any],
    *,
    route_key: str,
    task_type: str,
    provider: str,
    model: str,
    fallback_used: bool,
    allowed: bool,
    reason: str | None = None,
) -> None:
    diagnostics[route_key] = {
        "task_type": task_type,
        "provider": provider,
        "model": model,
        "fallback_used": fallback_used,
        "allowed": allowed,
        "reason": reason or "",
    }


def _log_route_decision(
    *,
    channel: str,
    source_ref: str,
    user_id: int,
    route_key: str,
    diagnostics: dict[str, Any],
) -> None:
    route = diagnostics.get(route_key) or {}
    logger.info(
        "Model routing: channel=%s source_ref=%s user_id=%s task_type=%s provider=%s model=%s fallback_used=%s allowed=%s reason=%s",
        channel,
        source_ref,
        user_id,
        route.get("task_type", ""),
        route.get("provider", ""),
        route.get("model", ""),
        bool(route.get("fallback_used")),
        bool(route.get("allowed")),
        route.get("reason", ""),
    )


def _log_bridge_event(
    *,
    route: str,
    user_id: int,
    source_ref: str,
    handler: str,
    ok: bool,
    latency_ms: int,
    fallback_used: bool = False,
    duplicate_skipped: bool = False,
    error_code: str | None = None,
    request_id: str | None = None,
) -> None:
    status = "ok"
    error_type = str(error_code or "")
    if duplicate_skipped:
        status = "degraded"
        if not error_type:
            error_type = "duplicate_skipped"
    elif not ok:
        status = "error"
        if not error_type:
            error_type = "bridge_error"
    if status in {"error", "degraded"} and error_type:
        _obs_record_error(
            handler=handler,
            error_type=error_type,
            source=source_ref,
            user_id=user_id,
        )
    logger.info(
        "%s",
        json.dumps(
            {
                "event": "openclaw_bridge",
                "route": route,
                "user_id": user_id,
                "source_ref": source_ref,
                "source": source_ref,
                "handler": handler,
                "action": route,
                "request_id": request_id or "",
                "ok": bool(ok),
                "status": status,
                "latency_ms": int(latency_ms),
                "duration_ms": int(latency_ms),
                "fallback_used": bool(fallback_used),
                "duplicate_skipped": bool(duplicate_skipped),
                "error_code": error_code or "",
                "error_type": error_type,
            },
            ensure_ascii=True,
            separators=(",", ":"),
        ),
    )


def _short_request_id(value: str | None = None) -> str:
    if value:
        return str(value)
    return uuid4().hex[:12]


def _voice_stt_fail_response(*, diagnostics: dict[str, Any], error_code: str) -> dict[str, Any]:
    user_id_raw = diagnostics.get("user_id")
    user_id = int(user_id_raw) if isinstance(user_id_raw, int) else 0
    is_voice_note = bool(diagnostics.get("telegram_voice_note"))
    if not diagnostics.get("fallback_reason"):
        if is_voice_note and error_code == "stt_empty":
            diagnostics["fallback_reason"] = "empty_transcript_voice_note"
        elif is_voice_note and error_code in {"stt_failed", "stt_timeout"}:
            diagnostics["fallback_reason"] = "stt_error"
        elif is_voice_note and error_code == "media_unavailable":
            diagnostics["fallback_reason"] = "voice_download_failed"
    diagnostics["fallback_reason"] = _normalize_voice_fallback_reason(diagnostics.get("fallback_reason"))
    diagnostics["final_outcome"] = "stt_empty" if error_code == "stt_empty" else ("fallback_no_media" if error_code == "media_unavailable" and not diagnostics.get("sttAttempted") else "stt_error")
    diagnostics["response_mode"] = "text"
    if is_voice_note and error_code == "stt_empty":
        text = _brevity_text(
            user_id,
            short="Не разобрал голосовое. Повтори чуть громче/длиннее.",
            normal=(
                "Не удалось распознать текст в голосовом сообщении. "
                "Попробуй повторить голосовое чуть громче, 2-3 секунды, без сильного шума."
            ),
        )
    elif is_voice_note:
        text = _brevity_text(
            user_id,
            short="Не удалось обработать голосовое. Повтори еще раз.",
            normal=(
                "Не удалось обработать сам файл голосового сообщения. "
                "Я теперь пытаюсь читать сам файл голосового. "
                "Если снова не вышло — повтори 2-3 секунды чуть громче."
            ),
        )
    else:
        text = _brevity_text(
            user_id,
            short="Не удалось распознать голос.",
            normal=STT_FAIL_FALLBACK_RU,
        )
    _log_telegram_voice_path(
        "telegram_voice_ingest",
        {
            "hasVoice": diagnostics.get("hasVoice"),
            "requestId": diagnostics.get("request_id"),
            "userIdHash": diagnostics.get("user_id_hash"),
            "messageKind": diagnostics.get("message_kind"),
            "hasAudio": diagnostics.get("hasAudio"),
            "hasDocument": diagnostics.get("hasDocument"),
            "hasText": diagnostics.get("hasText"),
            "hasTranscript": diagnostics.get("hasTranscript"),
            "voiceDuration": diagnostics.get("voiceDuration"),
            "mimeType": diagnostics.get("mimeType"),
            "telegramFileIdPresent": diagnostics.get("telegramFileIdPresent"),
            "telegramFileUniqueIdPresent": diagnostics.get("telegramFileUniqueIdPresent"),
            "downloaderName": diagnostics.get("downloader_name"),
            "downloaderPath": diagnostics.get("downloader_path"),
            "fileIdPresent": diagnostics.get("fileIdPresent"),
            "downloadAttempted": diagnostics.get("downloadAttempted"),
            "downloadOk": diagnostics.get("downloadOk"),
            "downloadBytes": diagnostics.get("downloadBytes"),
            "downloadError": diagnostics.get("download_error"),
            "mediaBytesPresent": diagnostics.get("mediaBytesPresent"),
            "mediaBytesLen": diagnostics.get("mediaBytesLen"),
            "mediaPathPresent": diagnostics.get("mediaPathPresent"),
            "mediaPathExists": diagnostics.get("mediaPathExists"),
            "mediaPathSize": diagnostics.get("mediaPathSize"),
            "mediaPathBase": diagnostics.get("mediaPathBase"),
            "transcriptLen": diagnostics.get("transcript_len"),
            "transcriptLooksAuto": diagnostics.get("transcript_looks_auto"),
            "sttAttempted": diagnostics.get("sttAttempted"),
            "sttOk": diagnostics.get("sttOk"),
            "sttSource": diagnostics.get("stt_source"),
            "sttResultLen": diagnostics.get("transcript_len"),
            "finalInputSource": diagnostics.get("stt_source"),
            "finalOutcome": diagnostics.get("final_outcome"),
            "fallbackReason": diagnostics.get("fallback_reason"),
            "responseMode": diagnostics.get("response_mode"),
        },
    )
    return _build_voice_response(
        handled=True,
        status="error",
        text=text,
        error_code=error_code,
        diagnostics=diagnostics,
    )


async def _synthesize_reply(
    reply_text: str,
    *,
    tts: TTSAdapter,
    tts_voice: str,
) -> tuple[str | None, bytes | None, str | None, dict[str, Any]]:
    try:
        tts_result: TTSResult = await asyncio.wait_for(
            tts.speak(reply_text or "", voice=tts_voice),
            timeout=BRIDGE_TTS_TIMEOUT_S,
        )
    except asyncio.TimeoutError:
        return None, None, None, {
            "tts_provider": "",
            "tts_error_code": "tts_timeout",
            "tts_error_message": "TTS timed out.",
            "tts_empty_output": False,
        }
    except Exception as exc:
        return None, None, None, {
            "tts_provider": "",
            "tts_error_code": "tts_failed",
            "tts_error_message": f"tts_exception:{_sanitize_text_for_logs(exc)}",
            "tts_empty_output": False,
        }
    diagnostics: dict[str, Any] = {
        "tts_provider": tts_result.provider_ref or "",
        "tts_error_code": tts_result.error_code,
        "tts_error_message": _sanitize_text_for_logs(tts_result.error_message or "", max_len=160),
    }
    if tts_result.ok and tts_result.audio_bytes and len(tts_result.audio_bytes) > 0:
        mime_type = tts_result.mime_type or "audio/ogg"
        return _guess_media_intent(mime_type), tts_result.audio_bytes, mime_type, diagnostics
    diagnostics["tts_empty_output"] = bool(tts_result.audio_bytes is not None and len(tts_result.audio_bytes) == 0)
    return None, None, None, diagnostics


def _detect_mode(user_id: int, mode_hint: str | None = None) -> str:
    lowered = (mode_hint or "").strip().lower()
    if lowered in {"tutor", "reflection", "default"}:
        return lowered
    if get_active_reflection_session(user_id):
        return "reflection"
    if get_active_tutor_session(user_id):
        return "tutor"
    if get_language_mode_preference(user_id) == "en_tutor":
        return "tutor"
    return "default"


async def dispatch_voice(
    *,
    user_id: int,
    source_ref: str | None = None,
    message_text: str | None = None,
    audio_bytes: bytes | None = None,
    audio_path: str | None = None,
    media_declared: bool = False,
    mode_hint: str | None = None,
    stt: STTAdapter | None = None,
    tts: TTSAdapter | None = None,
    tutor_service: EnglishTutorService | None = None,
    reflection_service: ReflectionVoiceService | None = None,
    input_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    source = source_ref or "openclaw"
    mode = _detect_mode(user_id, mode_hint)
    stt_language = STT_TUTOR_LANGUAGE if mode == "tutor" else STT_DEFAULT_LANGUAGE
    diagnostics: dict[str, Any] = {
        "source_ref": source,
        "mode": mode,
        "stt_language": stt_language,
        "user_id": user_id,
        "language_mode_pref": get_language_mode_preference(user_id),
        "brevity_pref": get_brevity_preference(user_id),
    }
    if isinstance(input_context, dict):
        diagnostics.update(
            {
                "request_id": str(input_context.get("requestId") or ""),
                "user_id_hash": str(input_context.get("userIdHash") or ""),
                "message_kind": str(input_context.get("messageKind") or ""),
                "hasVoice": bool(input_context.get("hasVoice")),
                "hasAudio": bool(input_context.get("hasAudio")),
                "hasDocument": bool(input_context.get("hasDocument")),
                "hasText": bool(input_context.get("hasText")),
                "hasTranscript": bool(input_context.get("hasTranscript")),
                "transcript_looks_auto": bool(input_context.get("transcriptLooksAuto")),
                "voiceDuration": input_context.get("voiceDuration"),
                "mimeType": str(input_context.get("mimeType") or ""),
                "fileIdPresent": bool(input_context.get("fileIdPresent")),
                "telegramFileIdPresent": bool(input_context.get("telegramFileIdPresent")),
                "telegramFileUniqueIdPresent": bool(input_context.get("telegramFileUniqueIdPresent")),
                "downloader_name": str(input_context.get("downloaderName") or ""),
                "downloader_path": str(input_context.get("downloaderPath") or ""),
                "downloadAttempted": bool(input_context.get("downloadAttempted")),
                "downloadOk": bool(input_context.get("downloadOk")),
                "downloadBytes": int(input_context.get("downloadBytes") or 0),
                "download_error": str(input_context.get("downloadError") or ""),
                "mediaBytesPresent": bool(input_context.get("mediaBytesPresent")),
                "mediaBytesLen": int(input_context.get("mediaBytesLen") or 0),
                "mediaPathPresent": bool(input_context.get("mediaPathPresent")),
                "mediaPathExists": input_context.get("mediaPathExists"),
                "mediaPathSize": input_context.get("mediaPathSize"),
                "mediaPathBase": str(input_context.get("mediaPathBase") or ""),
                "stt_source": str(input_context.get("sttSource") or ""),
                "telegram_voice_note": bool(input_context.get("telegramVoiceNote")),
                "telegram_media_kind": str(input_context.get("telegramMediaKind") or ""),
            }
        )
        if input_context.get("fallbackReason"):
            diagnostics["fallback_reason"] = _normalize_voice_fallback_reason(input_context.get("fallbackReason"))
    stt_adapter = stt or build_stt_adapter(settings)
    tts_adapter = tts or build_tts_adapter(settings)
    tutor = tutor_service or EnglishTutorService()
    reflection = reflection_service or ReflectionVoiceService()

    try:
        transcript_text = (message_text or "").strip()
        diagnostics["transcript_len"] = len(transcript_text)
        diagnostics["transcript_looks_auto"] = looks_like_auto_transcript(transcript_text)
        diagnostics["final_outcome"] = ""
        diagnostics["response_mode"] = ""
        if not diagnostics.get("stt_source"):
            diagnostics["stt_source"] = "transcript" if transcript_text else ""
        diagnostics["sttAttempted"] = False
        diagnostics["sttOk"] = False
        diagnostics["sttResultLen"] = 0

        if audio_bytes is None and audio_path:
            try:
                audio_file = Path(audio_path)
                if (not audio_file.exists()) or (not audio_file.is_file()):
                    diagnostics["audio_path_error"] = "not_found"
                    diagnostics["fallback_reason"] = _normalize_voice_fallback_reason(diagnostics.get("fallback_reason") or "stt_error")
                    return _voice_stt_fail_response(diagnostics=diagnostics, error_code="media_unavailable")
                if audio_file.stat().st_size <= 0:
                    diagnostics["audio_path_error"] = "empty_file"
                    diagnostics["fallback_reason"] = _normalize_voice_fallback_reason(diagnostics.get("fallback_reason") or "stt_error")
                    return _voice_stt_fail_response(diagnostics=diagnostics, error_code="media_unavailable")
                audio_bytes = audio_file.read_bytes()
                diagnostics["audio_path"] = str(audio_path)
                diagnostics["mediaPathPresent"] = True
                diagnostics["mediaPathBase"] = _safe_log_basename(audio_path)
                diagnostics["mediaPathExists"] = True
                diagnostics["mediaPathSize"] = len(audio_bytes)
                diagnostics["mediaBytesPresent"] = True
                diagnostics["mediaBytesLen"] = len(audio_bytes)
                diagnostics["downloadAttempted"] = bool(diagnostics.get("downloadAttempted")) or bool(
                    diagnostics.get("fileIdPresent")
                )
                diagnostics["downloadOk"] = True
                diagnostics["downloadBytes"] = len(audio_bytes)
            except OSError:
                diagnostics["fallback_reason"] = _normalize_voice_fallback_reason(diagnostics.get("fallback_reason") or "stt_error")
                return _voice_stt_fail_response(diagnostics=diagnostics, error_code="media_unavailable")

        if audio_bytes is not None:
            diagnostics["sttAttempted"] = True
            diagnostics["downloadBytes"] = int(diagnostics.get("downloadBytes") or len(audio_bytes))
            diagnostics["mediaBytesPresent"] = True
            diagnostics["mediaBytesLen"] = len(audio_bytes)
            try:
                stt_result = await asyncio.wait_for(
                    stt_adapter.transcribe(audio_bytes, language=stt_language),
                    timeout=BRIDGE_STT_TIMEOUT_S,
                )
            except asyncio.TimeoutError:
                diagnostics["stt_error_code"] = "stt_timeout"
                diagnostics["fallback_reason"] = _normalize_voice_fallback_reason(diagnostics.get("fallback_reason") or "stt_error")
                return _voice_stt_fail_response(diagnostics=diagnostics, error_code="stt_timeout")
            except Exception as exc:
                diagnostics["stt_error_code"] = "stt_failed"
                diagnostics["stt_error_message"] = f"stt_exception:{_sanitize_text_for_logs(exc)}"
                diagnostics["fallback_reason"] = _normalize_voice_fallback_reason(diagnostics.get("fallback_reason") or "stt_error")
                return _voice_stt_fail_response(diagnostics=diagnostics, error_code="stt_failed")
            diagnostics["stt_provider"] = stt_result.provider_ref or ""
            diagnostics["stt_error_code"] = stt_result.error_code
            if getattr(stt_result, "error_message", None):
                diagnostics["stt_error_message"] = _sanitize_text_for_logs(
                    getattr(stt_result, "error_message", ""),
                    max_len=160,
                )
            transcript = (stt_result.text or "").strip()
            if not stt_result.ok:
                if not transcript and not (stt_result.error_code or "").strip():
                    diagnostics["transcript_len"] = 0
                    diagnostics["sttOk"] = False
                    diagnostics["sttResultLen"] = 0
                    diagnostics["fallback_reason"] = diagnostics.get("fallback_reason") or (
                        "empty_transcript_voice_note" if diagnostics.get("telegram_voice_note") else "stt_empty"
                    )
                    diagnostics["fallback_reason"] = _normalize_voice_fallback_reason(diagnostics.get("fallback_reason"))
                    return _voice_stt_fail_response(
                        diagnostics=diagnostics,
                        error_code="stt_empty",
                    )
                diagnostics["fallback_reason"] = _normalize_voice_fallback_reason(diagnostics.get("fallback_reason") or "stt_error")
                return _voice_stt_fail_response(
                    diagnostics=diagnostics,
                    error_code=stt_result.error_code or "stt_failed",
                )
            diagnostics["transcript_len"] = len(transcript)
            diagnostics["sttOk"] = bool(transcript)
            diagnostics["sttResultLen"] = len(transcript)
            if not transcript:
                diagnostics["fallback_reason"] = diagnostics.get("fallback_reason") or (
                    "empty_transcript_voice_note" if diagnostics.get("telegram_voice_note") else "stt_empty"
                )
                diagnostics["fallback_reason"] = _normalize_voice_fallback_reason(diagnostics.get("fallback_reason"))
                return _voice_stt_fail_response(diagnostics=diagnostics, error_code="stt_empty")
            diagnostics["final_outcome"] = "stt_ok"
            _log_telegram_voice_path(
                "telegram_voice_ingest",
                {
                    "requestId": diagnostics.get("request_id"),
                    "userIdHash": diagnostics.get("user_id_hash"),
                    "messageKind": diagnostics.get("message_kind"),
                    "hasVoice": diagnostics.get("hasVoice"),
                    "hasAudio": diagnostics.get("hasAudio"),
                    "hasDocument": diagnostics.get("hasDocument"),
                    "hasText": diagnostics.get("hasText"),
                    "hasTranscript": diagnostics.get("hasTranscript"),
                    "transcriptLen": diagnostics.get("transcript_len"),
                    "transcriptLooksAuto": diagnostics.get("transcript_looks_auto"),
                    "voiceDuration": diagnostics.get("voiceDuration"),
                    "mimeType": diagnostics.get("mimeType"),
                    "telegramFileIdPresent": diagnostics.get("telegramFileIdPresent"),
                    "telegramFileUniqueIdPresent": diagnostics.get("telegramFileUniqueIdPresent"),
                    "downloaderName": diagnostics.get("downloader_name"),
                    "downloaderPath": diagnostics.get("downloader_path"),
                    "fileIdPresent": diagnostics.get("fileIdPresent"),
                    "downloadAttempted": diagnostics.get("downloadAttempted"),
                    "downloadOk": diagnostics.get("downloadOk"),
                    "downloadBytes": diagnostics.get("downloadBytes"),
                    "downloadError": diagnostics.get("download_error"),
                    "mediaBytesPresent": diagnostics.get("mediaBytesPresent"),
                    "mediaBytesLen": diagnostics.get("mediaBytesLen"),
                    "mediaPathPresent": diagnostics.get("mediaPathPresent"),
                    "mediaPathExists": diagnostics.get("mediaPathExists"),
                    "mediaPathSize": diagnostics.get("mediaPathSize"),
                    "mediaPathBase": diagnostics.get("mediaPathBase"),
                    "sttAttempted": diagnostics.get("sttAttempted"),
                    "sttOk": diagnostics.get("sttOk"),
                    "sttSource": diagnostics.get("stt_source"),
                    "sttResultLen": diagnostics.get("transcript_len"),
                    "finalInputSource": diagnostics.get("stt_source"),
                    "finalOutcome": diagnostics.get("final_outcome"),
                    "fallbackReason": diagnostics.get("fallback_reason"),
                    "responseMode": diagnostics.get("response_mode"),
                },
            )
            if mode in {"tutor", "reflection"}:
                try:
                    ingest_message_event(
                        {
                            "source_type": "voice",
                            "user_id": str(user_id),
                            "channel": "openclaw",
                            "source_ref": source,
                            "text": transcript,
                            "language": stt_language,
                            "tags": ["bridge", "voice"],
                            "importance": "normal",
                            "needs_indexing": True,
                        }
                    )
                except Exception:
                    pass

            if mode == "reflection":
                route = resolve_route(TASK_VOICE_REPLY_REASONING, settings)
                _attach_route_diagnostics(
                    diagnostics,
                    route_key="reasoning_route",
                    task_type=route.task_type,
                    provider=route.selected_provider,
                    model=route.selected_model,
                    fallback_used=route.fallback_used,
                    allowed=route.allowed,
                    reason=route.reason,
                )
                _log_route_decision(
                    channel="voice",
                    source_ref=source,
                    user_id=user_id,
                    route_key="reasoning_route",
                    diagnostics=diagnostics,
                )
                if not route.allowed:
                    return _build_voice_response(
                        handled=True,
                        status="error",
                        text=REASONING_UNAVAILABLE_RU,
                        error_code="reasoning_provider_unavailable",
                        diagnostics=diagnostics,
                    )
                reply_text, error = await reflection.handle_user_turn(user_id, transcript)
                if error:
                    return _build_voice_response(
                        handled=True,
                        status="error",
                        text=error,
                        error_code="reflection_error",
                        diagnostics=diagnostics,
                    )
                if get_voice_reply_preference(user_id):
                    intent, tts_bytes, mime_type, tts_diag = await _synthesize_reply(
                        reply_text or "",
                        tts=tts_adapter,
                        tts_voice=settings.tts_voice,
                    )
                    diagnostics.update(tts_diag)
                    diagnostics["response_mode"] = "voice" if intent == "sendVoice" else ("audio" if intent == "sendAudio" else "text")
                else:
                    intent, tts_bytes, mime_type = None, None, None
                    diagnostics["voice_reply_disabled"] = True
                    diagnostics["tts_skipped_reason"] = "voice_pref_off"
                    diagnostics["response_mode"] = "text"
                return _build_voice_response(
                    handled=True,
                    text=reply_text or "",
                    audio_intent=intent,
                    audio_bytes=tts_bytes,
                    mime_type=mime_type,
                    diagnostics=diagnostics,
                )

            if mode == "tutor":
                route = resolve_route(TASK_VOICE_REPLY_REASONING, settings)
                _attach_route_diagnostics(
                    diagnostics,
                    route_key="reasoning_route",
                    task_type=route.task_type,
                    provider=route.selected_provider,
                    model=route.selected_model,
                    fallback_used=route.fallback_used,
                    allowed=route.allowed,
                    reason=route.reason,
                )
                _log_route_decision(
                    channel="voice",
                    source_ref=source,
                    user_id=user_id,
                    route_key="reasoning_route",
                    diagnostics=diagnostics,
                )
                if not route.allowed:
                    return _build_voice_response(
                        handled=True,
                        status="error",
                        text=REASONING_UNAVAILABLE_RU,
                        error_code="reasoning_provider_unavailable",
                        diagnostics=diagnostics,
                    )
                reply_text, error = await tutor.handle_user_turn(user_id, transcript)
                if error:
                    return _build_voice_response(
                        handled=True,
                        status="error",
                        text=error,
                        error_code="tutor_error",
                        diagnostics=diagnostics,
                    )
                if get_voice_reply_preference(user_id):
                    intent, tts_bytes, mime_type, tts_diag = await _synthesize_reply(
                        reply_text or "",
                        tts=tts_adapter,
                        tts_voice=settings.tts_voice,
                    )
                    diagnostics.update(tts_diag)
                    diagnostics["response_mode"] = "voice" if intent == "sendVoice" else ("audio" if intent == "sendAudio" else "text")
                else:
                    intent, tts_bytes, mime_type = None, None, None
                    diagnostics["voice_reply_disabled"] = True
                    diagnostics["tts_skipped_reason"] = "voice_pref_off"
                    diagnostics["response_mode"] = "text"
                return _build_voice_response(
                    handled=True,
                    text=reply_text or "",
                    audio_intent=intent,
                    audio_bytes=tts_bytes,
                    mime_type=mime_type,
                    diagnostics=diagnostics,
                )

            storage = VaultStorage(settings.vault_path)
            now = datetime.utcnow()
            storage.append_to_daily(transcript, now, "[voice]")
            session = SessionStore(settings.vault_path)
            session.append(user_id, "voice", text=transcript, source_ref=source)
            diagnostics["response_mode"] = "text"
            return _build_voice_response(
                handled=True,
                text=_brevity_text(
                    user_id,
                    short=f"Сохранено: {transcript}",
                    normal=f"Сохранено в дневник: {transcript}",
                ),
                diagnostics=diagnostics,
            )

        if media_declared:
            if diagnostics.get("fallback_reason") == "unsupported_media_shape" and transcript_text:
                diagnostics["stt_source"] = "transcript"
                diagnostics["final_outcome"] = "fallback_transcript"
                diagnostics["response_mode"] = "text"
            else:
                diagnostics["media_declared_without_bytes"] = True
                diagnostics["fallback_reason"] = _normalize_voice_fallback_reason(diagnostics.get("fallback_reason") or "media_declared_without_bytes")
                return _voice_stt_fail_response(diagnostics=diagnostics, error_code="media_unavailable")

        if looks_like_auto_transcript(transcript_text):
            route = resolve_route(TASK_LIGHT_CLASSIFICATION, settings)
            _attach_route_diagnostics(
                diagnostics,
                route_key="classification_route",
                task_type=route.task_type,
                provider=route.selected_provider,
                model=route.selected_model,
                fallback_used=route.fallback_used,
                allowed=route.allowed,
                reason=route.reason,
            )
            _log_route_decision(
                channel="voice",
                source_ref=source,
                user_id=user_id,
                route_key="classification_route",
                diagnostics=diagnostics,
            )
            if not route.allowed:
                return _build_voice_response(handled=False, diagnostics=diagnostics)
            diagnostics["transcript_only_warning"] = True
            diagnostics["stt_source"] = diagnostics.get("stt_source") or "transcript"
            diagnostics["fallback_reason"] = _normalize_voice_fallback_reason(diagnostics.get("fallback_reason") or "transcript_only_auto")
            diagnostics["final_outcome"] = "fallback_transcript"
            diagnostics["response_mode"] = "text"
            _log_telegram_voice_path(
                "telegram_voice_ingest",
                {
                    "requestId": diagnostics.get("request_id"),
                    "userIdHash": diagnostics.get("user_id_hash"),
                    "messageKind": diagnostics.get("message_kind"),
                    "hasVoice": diagnostics.get("hasVoice"),
                    "hasAudio": diagnostics.get("hasAudio"),
                    "hasDocument": diagnostics.get("hasDocument"),
                    "hasText": diagnostics.get("hasText"),
                    "hasTranscript": diagnostics.get("hasTranscript"),
                    "transcriptLen": diagnostics.get("transcript_len"),
                    "transcriptLooksAuto": diagnostics.get("transcript_looks_auto"),
                    "voiceDuration": diagnostics.get("voiceDuration"),
                    "mimeType": diagnostics.get("mimeType"),
                    "telegramFileIdPresent": diagnostics.get("telegramFileIdPresent"),
                    "telegramFileUniqueIdPresent": diagnostics.get("telegramFileUniqueIdPresent"),
                    "downloaderName": diagnostics.get("downloader_name"),
                    "downloaderPath": diagnostics.get("downloader_path"),
                    "fileIdPresent": diagnostics.get("fileIdPresent"),
                    "downloadAttempted": diagnostics.get("downloadAttempted"),
                    "downloadOk": diagnostics.get("downloadOk"),
                    "downloadBytes": diagnostics.get("downloadBytes"),
                    "downloadError": diagnostics.get("download_error"),
                    "mediaBytesPresent": diagnostics.get("mediaBytesPresent"),
                    "mediaBytesLen": diagnostics.get("mediaBytesLen"),
                    "mediaPathPresent": diagnostics.get("mediaPathPresent"),
                    "mediaPathExists": diagnostics.get("mediaPathExists"),
                    "mediaPathSize": diagnostics.get("mediaPathSize"),
                    "mediaPathBase": diagnostics.get("mediaPathBase"),
                    "sttAttempted": diagnostics.get("sttAttempted"),
                    "sttOk": diagnostics.get("sttOk"),
                    "sttSource": diagnostics.get("stt_source"),
                    "sttResultLen": diagnostics.get("sttResultLen"),
                    "finalInputSource": diagnostics.get("stt_source"),
                    "finalOutcome": diagnostics.get("final_outcome"),
                    "fallbackReason": diagnostics.get("fallback_reason"),
                    "responseMode": diagnostics.get("response_mode"),
                },
            )
            return _build_voice_response(
                handled=True,
                text=_brevity_text(
                    user_id,
                    short="Пришлите голос, а не авто-транскрипт.",
                    normal=TRANSCRIPT_WARNING,
                ),
                diagnostics=diagnostics,
            )

        if not transcript_text:
            diagnostics["fallback_reason"] = _normalize_voice_fallback_reason(diagnostics.get("fallback_reason") or "no_voice_content")
            diagnostics["final_outcome"] = "fallback_no_media"
            diagnostics["response_mode"] = "text"
            return _build_voice_response(handled=False, diagnostics=diagnostics)
        if mode in {"tutor", "reflection"}:
            try:
                ingest_message_event(
                    {
                        "source_type": "text",
                        "user_id": str(user_id),
                        "channel": "openclaw",
                        "source_ref": source,
                        "text": transcript_text,
                        "language": "ru" if mode != "tutor" else "en",
                        "tags": ["bridge", "text"],
                        "importance": "normal",
                        "needs_indexing": True,
                    }
                )
            except Exception:
                pass

        if mode == "reflection":
            route = resolve_route(TASK_MAIN_REASONING, settings)
            _attach_route_diagnostics(
                diagnostics,
                route_key="reasoning_route",
                task_type=route.task_type,
                provider=route.selected_provider,
                model=route.selected_model,
                fallback_used=route.fallback_used,
                allowed=route.allowed,
                reason=route.reason,
            )
            _log_route_decision(
                channel="text",
                source_ref=source,
                user_id=user_id,
                route_key="reasoning_route",
                diagnostics=diagnostics,
            )
            if not route.allowed:
                return _build_voice_response(
                    handled=True,
                    status="error",
                    text=REASONING_UNAVAILABLE_RU,
                    error_code="reasoning_provider_unavailable",
                    diagnostics=diagnostics,
                )
            reply_text, error = await reflection.handle_user_turn(user_id, transcript_text)
            if error:
                return _build_voice_response(
                    handled=True,
                    status="error",
                    text=error,
                    error_code="reflection_error",
                    diagnostics=diagnostics,
                )
            diagnostics["response_mode"] = "text"
            return _build_voice_response(
                handled=True,
                text=reply_text or "",
                diagnostics=diagnostics,
            )

        if mode == "tutor":
            route = resolve_route(TASK_MAIN_REASONING, settings)
            _attach_route_diagnostics(
                diagnostics,
                route_key="reasoning_route",
                task_type=route.task_type,
                provider=route.selected_provider,
                model=route.selected_model,
                fallback_used=route.fallback_used,
                allowed=route.allowed,
                reason=route.reason,
            )
            _log_route_decision(
                channel="text",
                source_ref=source,
                user_id=user_id,
                route_key="reasoning_route",
                diagnostics=diagnostics,
            )
            if not route.allowed:
                return _build_voice_response(
                    handled=True,
                    status="error",
                    text=REASONING_UNAVAILABLE_RU,
                    error_code="reasoning_provider_unavailable",
                    diagnostics=diagnostics,
                )
            reply_text, error = await tutor.handle_user_turn(user_id, transcript_text)
            if error:
                return _build_voice_response(
                    handled=True,
                    status="error",
                    text=error,
                    error_code="tutor_error",
                    diagnostics=diagnostics,
                )
            diagnostics["response_mode"] = "text"
            return _build_voice_response(
                handled=True,
                text=reply_text or "",
                diagnostics=diagnostics,
            )

        return _build_voice_response(handled=False, diagnostics=diagnostics)
    except Exception:
        return _build_voice_response(
            handled=True,
            status="error",
            text=_brevity_text(
                user_id,
                short="Ошибка. Попробуйте позже.",
                normal=INTERNAL_ERROR_RU,
            ),
            error_code="internal_error",
            diagnostics=diagnostics,
        )


def dispatch_voice_sync(
    *,
    user_id: int,
    source_ref: str | None = None,
    message_text: str | None = None,
    audio_bytes: bytes | None = None,
    audio_path: str | None = None,
    media_declared: bool = False,
    mode_hint: str | None = None,
    request_id: str | None = None,
    input_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    req_id = _short_request_id(request_id)
    source_key = str(source_ref or "openclaw")
    duplicate_key = f"voice:{user_id}:{source_key}:{bool(audio_bytes)}:{bool(audio_path)}:{bool(message_text and str(message_text).strip())}:{str(mode_hint or '').lower()}"
    cached = _duplicate_guard_get(duplicate_key)
    if isinstance(cached, dict):
        payload = dict(cached)
        payload["meta"] = dict(payload.get("meta") or {})
        payload["meta"]["duplicate_skipped"] = True
        _log_bridge_event(
            route="voice",
            user_id=user_id,
            source_ref=source_key,
            handler="dispatch_voice_sync:duplicate_skip",
            ok=bool(payload.get("handled")) and str(payload.get("status") or "ok") == "ok",
            latency_ms=0,
            duplicate_skipped=True,
            error_code=str(payload.get("error_code") or ""),
            request_id=req_id,
        )
        return payload
    started = time.perf_counter()
    _log_bridge_event(
        route="voice",
        user_id=user_id,
        source_ref=source_key,
        handler="dispatch_voice_sync:start",
        ok=True,
        latency_ms=0,
        fallback_used=False,
        error_code="",
        request_id=req_id,
    )
    response = asyncio.run(
        dispatch_voice(
            user_id=user_id,
            source_ref=source_ref,
            message_text=message_text,
            audio_bytes=audio_bytes,
            audio_path=audio_path,
            media_declared=media_declared,
            mode_hint=mode_hint,
            input_context=input_context,
        )
    )
    diagnostics = response.get("diagnostics") or {}
    response["meta"] = dict(response.get("meta") or {})
    response["meta"]["duplicate_skipped"] = False
    _log_bridge_event(
        route="voice",
        user_id=user_id,
        source_ref=source_key,
        handler="dispatch_voice_sync",
        ok=bool(response.get("handled")) and str(response.get("status") or "ok") == "ok",
        latency_ms=int((time.perf_counter() - started) * 1000),
        fallback_used=bool(diagnostics.get("tts_empty_output")) or bool(response.get("error_code")),
        error_code=str(response.get("error_code") or ""),
        request_id=req_id,
    )
    _duplicate_guard_put(duplicate_key, dict(response))
    return response


def dispatch_voice_from_message(
    message: dict[str, Any],
    *,
    user_id: int,
    request_id: str | None = None,
) -> dict[str, Any]:
    normalized = _normalize_voice_payload(message)
    audio_bytes = normalized.get("audio_bytes")
    audio_path = normalized.get("audio_path")
    text = normalized.get("text")
    media_declared = bool(normalized.get("media_declared"))
    input_context = normalized.get("path_meta") if isinstance(normalized.get("path_meta"), dict) else None
    if isinstance(input_context, dict):
        if request_id and not input_context.get("requestId"):
            input_context["requestId"] = str(request_id)
        if not input_context.get("userIdHash"):
            input_context["userIdHash"] = _hash_user_id_for_logs(user_id)
        _log_telegram_voice_path("telegram_stt_source_select", input_context)
    source_ref = str(message.get("source_ref") or "") or None
    if not source_ref:
        chat_id = message.get("chat_id")
        message_id = message.get("message_id")
        if chat_id is not None and message_id is not None:
            source_ref = f"{chat_id}:{message_id}"
    mode_hint = message.get("mode")
    return dispatch_voice_sync(
        user_id=user_id,
        source_ref=source_ref,
        message_text=text,
        audio_bytes=audio_bytes,
        audio_path=audio_path,
        media_declared=media_declared,
        mode_hint=str(mode_hint) if mode_hint is not None else None,
        request_id=request_id,
        input_context=input_context,
    )



