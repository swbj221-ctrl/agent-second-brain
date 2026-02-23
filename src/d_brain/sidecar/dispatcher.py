"""Sidecar request dispatcher for Stage 2 ingestion."""

from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from d_brain.config import Settings, get_settings

from .errors import SidecarError
from .ingestion import ingest_payload
from .models import (
    EventCreatePayload,
    EventListPayload,
    EventParsePayload,
    EventUpdateStatusPayload,
    IngestPayload,
    ReminderListPayload,
    ReminderUpdateStatusPayload,
    SidecarErrorData,
    SidecarRequest,
    SidecarResponse,
)
from .plans import (
    create_event_with_default_reminder,
    parse_event_text,
    trigger_due_reminders,
    update_event_status,
    update_reminder_status,
)
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
        store = SQLiteStore(active_settings.db_path)
        if request.action == "ingest":
            payload = IngestPayload.model_validate(request.payload or {})
            data = ingest_payload(payload, store)
        elif request.action == "event_create":
            payload = EventCreatePayload.model_validate(request.payload or {})
            data = create_event_with_default_reminder(payload, store)
        elif request.action == "event_list":
            payload = EventListPayload.model_validate(request.payload or {})
            data = {"events": store.list_events(payload.status, payload.limit, payload.offset)}
        elif request.action == "event_update_status":
            payload = EventUpdateStatusPayload.model_validate(request.payload or {})
            data = update_event_status(payload, store)
        elif request.action == "event_parse":
            payload = EventParsePayload.model_validate(request.payload or {})
            data = parse_event_text(payload, store)
        elif request.action == "reminder_list":
            payload = ReminderListPayload.model_validate(request.payload or {})
            data = {
                "reminders": store.list_reminders(
                    payload.status, payload.due_before, payload.limit, payload.offset
                )
            }
        elif request.action == "reminder_update_status":
            payload = ReminderUpdateStatusPayload.model_validate(request.payload or {})
            data = update_reminder_status(payload, store)
        elif request.action == "reminder_trigger_due":
            data = trigger_due_reminders(store)
        else:
            raise SidecarError("invalid_payload", f"Unsupported action: {request.action}")
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
