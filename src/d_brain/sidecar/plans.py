"""Rule-first plans and reminders helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .errors import SidecarError
from .models import (
    EventCreatePayload,
    EventParsePayload,
    EventUpdateStatusPayload,
    ReminderUpdateStatusPayload,
)
from .store import SQLiteStore, compute_hash, utc_now

DEFAULT_REMINDER_OFFSET = timedelta(hours=1)
MAX_PARSE_EXCERPT = 200


@dataclass(slots=True)
class ParsedEvent:
    title: str
    start_at: str | None
    remind_at: str | None


def parse_iso_datetime(value: str) -> str:
    cleaned = value.strip()
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(cleaned)
    except ValueError as exc:
        raise SidecarError("invalid_payload", f"Invalid datetime: {value}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def default_reminder_at(start_at: str | None) -> str:
    if start_at:
        return start_at
    now = datetime.now(timezone.utc).replace(microsecond=0)
    return (now + DEFAULT_REMINDER_OFFSET).isoformat()


def clamp_excerpt(text: str) -> str:
    trimmed = text.strip()
    if len(trimmed) <= MAX_PARSE_EXCERPT:
        return trimmed
    return trimmed[:MAX_PARSE_EXCERPT]


def parse_event_text(payload: EventParsePayload, store: SQLiteStore) -> dict[str, str | None]:
    """Parse text using a strict rule: 'title | <iso datetime>'"""
    text = payload.text.strip()
    excerpt = clamp_excerpt(text)
    input_hash = compute_hash(text) if text else None
    input_length = len(text)
    error_message = None
    parsed_event: ParsedEvent | None = None

    if "|" in text:
        parts = [part.strip() for part in text.split("|", 1)]
        if len(parts) == 2 and parts[0] and parts[1]:
            try:
                start_at = parse_iso_datetime(parts[1])
                parsed_event = ParsedEvent(
                    title=parts[0],
                    start_at=start_at,
                    remind_at=default_reminder_at(start_at),
                )
            except SidecarError as exc:
                error_message = exc.message
        else:
            error_message = "Parse rule requires 'title | <iso datetime>'."
    else:
        error_message = "Parse rule requires 'title | <iso datetime>'."

    parse_status = "ok" if parsed_event else "failed"
    store.create_parse_log(
        source_type=payload.source_type,
        source_ref=payload.source_ref,
        input_excerpt=excerpt,
        input_hash=input_hash,
        input_length=input_length,
        parse_status=parse_status,
        error_message=error_message,
        event_id=None,
    )

    if not parsed_event:
        raise SidecarError("invalid_payload", error_message or "Unable to parse event.")

    return {
        "title": parsed_event.title,
        "start_at": parsed_event.start_at,
        "remind_at": parsed_event.remind_at,
    }


def create_event_with_default_reminder(
    payload: EventCreatePayload,
    store: SQLiteStore,
) -> dict[str, int | str | None]:
    title = payload.title.strip()
    if not title:
        raise SidecarError("invalid_payload", "Title is required.")

    start_at = parse_iso_datetime(payload.start_at) if payload.start_at else None
    end_at = parse_iso_datetime(payload.end_at) if payload.end_at else None
    remind_at = parse_iso_datetime(payload.remind_at) if payload.remind_at else None
    if remind_at is None:
        remind_at = default_reminder_at(start_at)

    event_id = store.create_event(
        title=title,
        body=payload.body,
        start_at=start_at,
        end_at=end_at,
        status="planned",
        source_type=payload.source_type,
        source_ref=payload.source_ref,
    )
    reminder_id = store.create_reminder(
        event_id=event_id,
        remind_at=remind_at,
        status="pending",
    )
    return {
        "event_id": event_id,
        "reminder_id": reminder_id,
        "remind_at": remind_at,
    }


def update_event_status(
    payload: EventUpdateStatusPayload,
    store: SQLiteStore,
) -> dict[str, int | str]:
    store.update_event_status(payload.event_id, payload.status)
    return {"event_id": payload.event_id, "status": payload.status}


def update_reminder_status(
    payload: ReminderUpdateStatusPayload,
    store: SQLiteStore,
) -> dict[str, int | str]:
    store.update_reminder_status(payload.reminder_id, payload.status)
    return {"reminder_id": payload.reminder_id, "status": payload.status}


def trigger_due_reminders(store: SQLiteStore) -> dict[str, int]:
    now_iso = utc_now()
    due = store.list_due_reminders(now_iso)
    for reminder in due:
        store.mark_reminder_triggered(reminder["id"])
    return {"triggered": len(due)}
