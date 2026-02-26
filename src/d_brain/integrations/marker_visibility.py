"""Shared observable marker emitter for OpenClaw live verification paths."""

from __future__ import annotations

import json
import os
import sys
from typing import Any


_TRUE_VALUES = {"1", "true", "yes", "on"}


def _is_stream_fallback_enabled() -> bool:
    raw = str(os.getenv("OPENCLAW_MARKER_STREAM_FALLBACK", "1") or "").strip().lower()
    return raw in _TRUE_VALUES


def serialize_marker(marker: dict[str, Any]) -> str:
    payload = dict(marker or {})
    request_id = str(payload.get("requestId") or payload.get("request_id") or "").strip()
    if request_id:
        payload.setdefault("requestId", request_id)
        payload.setdefault("request_id", request_id)
        # Keep request-id discoverable in raw wrapped log lines where JSON keys can
        # be multiply escaped by upper runtime sinks (openclaw logs --json --plain).
        payload.setdefault("requestIdTag", f"requestId={request_id}")
        payload.setdefault("request_id_tag", f"request_id={request_id}")
    return json.dumps(payload, ensure_ascii=True, separators=(",", ":"))


def emit_observable_marker(
    marker: dict[str, Any] | None,
    *,
    logger_obj: Any = None,
    level: str = "info",
    stream_fallback: bool | None = None,
) -> str:
    if not isinstance(marker, dict):
        return ""
    line = ""
    try:
        line = serialize_marker(marker)
    except Exception:
        return ""

    if logger_obj is not None:
        try:
            log_fn = getattr(logger_obj, str(level or "info").lower(), None) or logger_obj.info
            log_fn("%s", line)
        except Exception:
            pass

    use_stream = _is_stream_fallback_enabled() if stream_fallback is None else bool(stream_fallback)
    if use_stream:
        try:
            print(line, file=sys.stderr, flush=True)
        except Exception:
            try:
                print(line, file=sys.stdout, flush=True)
            except Exception:
                pass
    return line
