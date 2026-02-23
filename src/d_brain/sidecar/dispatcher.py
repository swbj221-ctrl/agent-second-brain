"""Sidecar request dispatcher for Stage 2 ingestion."""

from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from d_brain.config import Settings, get_settings

from .errors import SidecarError
from .ingestion import ingest_payload
from .models import IngestPayload, SidecarErrorData, SidecarRequest, SidecarResponse
from .store import SQLiteStore


def payload_size_bytes(payload: dict[str, Any]) -> int:
    """Calculate JSON-encoded payload size in bytes."""
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=True)
    return len(raw.encode("utf-8"))


def enforce_payload_limit(payload: dict[str, Any] | None, limit_bytes: int) -> None:
    if not payload:
        return
    if payload_size_bytes(payload) > limit_bytes:
        raise SidecarError(
            "payload_too_large",
            f"Payload exceeds limit of {limit_bytes} bytes.",
        )


def handle_request(
    raw_request: dict[str, Any],
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Handle a sidecar request and return a response dict."""
    active_settings = settings or get_settings()
    try:
        request = SidecarRequest.model_validate(raw_request)
        enforce_payload_limit(request.payload, active_settings.sidecar_payload_limit_bytes)
        if request.action != "ingest":
            raise SidecarError("invalid_payload", f"Unsupported action: {request.action}")
        payload = IngestPayload.model_validate(request.payload or {})
        store = SQLiteStore(active_settings.db_path)
        data = ingest_payload(payload, store)
        response = SidecarResponse(
            request_id=request.request_id,
            status="ok",
            data=data,
        )
    except SidecarError as exc:
        response = SidecarResponse(
            request_id=raw_request.get("request_id", "unknown"),
            status="error",
            error=SidecarErrorData(code=exc.code, message=exc.message),
        )
    except ValidationError as exc:
        response = SidecarResponse(
            request_id=raw_request.get("request_id", "unknown"),
            status="error",
            error=SidecarErrorData(code="invalid_payload", message=str(exc)),
        )
    return response.model_dump()
