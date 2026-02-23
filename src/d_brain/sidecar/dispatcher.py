"""Sidecar request dispatcher for Stage 2 ingestion."""

from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from d_brain.config import Settings, get_settings

from .errors import SidecarError
from .ingestion import ingest_payload
from .models import (
    EnglishSessionClosePayload,
    EnglishSessionCreatePayload,
    EnglishSessionTurnAppendPayload,
    EnglishTopicAddPayload,
    EnglishTopicListPayload,
    EnglishWordAddPayload,
    EnglishWordListPayload,
    DigestGeneratePayload,
    DigestGetLatestPayload,
    DigestListPayload,
    CodexLimitsSettingsGetPayload,
    CodexLimitsSettingsUpsertPayload,
    CodexUsageListPayload,
    CodexUsageLogAddPayload,
    CodexUsageStatusGetPayload,
    EventCreatePayload,
    EventListPayload,
    EventParsePayload,
    EventUpdateStatusPayload,
    HeartbeatTickPayload,
    IngestPayload,
    NewsItemIngestPayload,
    NewsItemSavePayload,
    NewsItemSummarizePayload,
    NewsBriefingGeneratePayload,
    NewsBriefingGetPayload,
    NewsBriefingListPayload,
    NewsSectionCreatePayload,
    NewsSectionListPayload,
    NewsSectionUpdatePayload,
    NewsSourceCreatePayload,
    NewsSourceListPayload,
    NewsSourceUpdatePayload,
    ReflectionSessionClosePayload,
    ReflectionSessionCreatePayload,
    ReflectionSessionListPayload,
    ReflectionSessionTurnAppendPayload,
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
from .news import generate_manual_briefing, summarize_news_item
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
        elif request.action == "english_word_add":
            payload = EnglishWordAddPayload.model_validate(request.payload or {})
            word_id = store.create_english_word(payload.word)
            data = {"word_id": word_id}
        elif request.action == "english_word_list":
            payload = EnglishWordListPayload.model_validate(request.payload or {})
            data = {"words": store.list_english_words(payload.limit, payload.offset)}
        elif request.action == "english_topic_add":
            payload = EnglishTopicAddPayload.model_validate(request.payload or {})
            topic_id = store.create_english_topic(payload.name)
            data = {"topic_id": topic_id}
        elif request.action == "english_topic_list":
            payload = EnglishTopicListPayload.model_validate(request.payload or {})
            data = {"topics": store.list_english_topics(payload.limit, payload.offset)}
        elif request.action == "english_session_create":
            payload = EnglishSessionCreatePayload.model_validate(request.payload or {})
            session_id = store.create_english_session(payload.topic_id)
            data = {"session_id": session_id}
        elif request.action == "english_session_turn_append":
            payload = EnglishSessionTurnAppendPayload.model_validate(request.payload or {})
            turn_id = store.append_english_session_turn(
                payload.session_id,
                payload.role,
                payload.content,
            )
            data = {"turn_id": turn_id}
        elif request.action == "english_session_close":
            payload = EnglishSessionClosePayload.model_validate(request.payload or {})
            summary = (payload.summary_text or "").strip() or "Summary pending."
            store.close_english_session(payload.session_id, summary)
            data = {"session_id": payload.session_id, "summary_text": summary}
        elif request.action == "reflection_session_create":
            ReflectionSessionCreatePayload.model_validate(request.payload or {})
            session_id = store.create_reflection_session()
            data = {"session_id": session_id}
        elif request.action == "reflection_turn_append":
            payload = ReflectionSessionTurnAppendPayload.model_validate(request.payload or {})
            turn_id = store.append_reflection_turn(
                payload.session_id,
                payload.role,
                payload.content,
            )
            data = {"turn_id": turn_id}
        elif request.action == "reflection_session_close":
            payload = ReflectionSessionClosePayload.model_validate(request.payload or {})
            summary = (payload.summary_text or "").strip() or "Summary pending."
            store.close_reflection_session(payload.session_id, summary)
            data = {"session_id": payload.session_id, "summary_text": summary}
        elif request.action == "reflection_session_list":
            payload = ReflectionSessionListPayload.model_validate(request.payload or {})
            data = {
                "sessions": store.list_reflection_sessions(
                    payload.status, payload.limit, payload.offset
                )
            }
        elif request.action == "heartbeat_tick":
            payload = HeartbeatTickPayload.model_validate(request.payload or {})
            data = store.create_heartbeat_log(
                event_type=payload.event_type,
                event_source=payload.event_source,
                event_details=payload.event_details,
            )
        elif request.action == "digest_generate":
            payload = DigestGeneratePayload.model_validate(request.payload or {})
            if payload.digest_type != "system_state":
                raise SidecarError(
                    "invalid_payload",
                    f"Unsupported digest_type: {payload.digest_type}",
                )
            data = store.generate_system_state_digest()
        elif request.action == "digest_get_latest":
            DigestGetLatestPayload.model_validate(request.payload or {})
            data = store.get_latest_digest()
        elif request.action == "digest_list":
            payload = DigestListPayload.model_validate(request.payload or {})
            data = {"digests": store.list_digests(payload.limit, payload.offset)}
        elif request.action == "codex_usage_log_add":
            payload = CodexUsageLogAddPayload.model_validate(request.payload or {})
            data = store.create_codex_usage_log(
                scope_key=payload.scope_key,
                request_id=payload.request_id,
                user_id=payload.user_id,
                model_ref=payload.model_ref,
                context=payload.context,
                tokens_in=payload.tokens_in,
                tokens_out=payload.tokens_out,
                total_tokens=payload.total_tokens,
                latency_ms=payload.latency_ms,
                request_count=payload.request_count,
                metadata=payload.metadata,
            )
        elif request.action == "codex_usage_status_get":
            payload = CodexUsageStatusGetPayload.model_validate(request.payload or {})
            data = store.get_codex_usage_status(payload.scope_key)
        elif request.action == "codex_limits_settings_upsert":
            payload = CodexLimitsSettingsUpsertPayload.model_validate(request.payload or {})
            data = store.upsert_codex_limits_settings(
                scope_key=payload.scope_key,
                window_hours=payload.window_hours,
                max_tokens=payload.max_tokens,
                max_requests=payload.max_requests,
                max_latency_ms=payload.max_latency_ms,
                warn_ratio=payload.warn_ratio,
                critical_ratio=payload.critical_ratio,
            )
        elif request.action == "codex_limits_settings_get":
            payload = CodexLimitsSettingsGetPayload.model_validate(request.payload or {})
            data = store.get_codex_limits_settings(payload.scope_key)
            if data is None:
                raise SidecarError(
                    "not_found",
                    f"Codex limits settings not found for scope {payload.scope_key}.",
                )
        elif request.action == "codex_usage_list":
            payload = CodexUsageListPayload.model_validate(request.payload or {})
            data = {
                "usage_logs": store.list_codex_usage_logs(
                    payload.scope_key, payload.limit, payload.offset
                )
            }
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
        elif request.action == "news_section_create":
            payload = NewsSectionCreatePayload.model_validate(request.payload or {})
            section_id = store.create_news_section(
                payload.name, payload.description, payload.status
            )
            data = {"section_id": section_id}
        elif request.action == "news_section_list":
            payload = NewsSectionListPayload.model_validate(request.payload or {})
            data = {
                "sections": store.list_news_sections(
                    payload.status, payload.limit, payload.offset
                )
            }
        elif request.action == "news_section_update":
            payload = NewsSectionUpdatePayload.model_validate(request.payload or {})
            store.update_news_section(
                payload.section_id,
                payload.name,
                payload.description,
                payload.status,
            )
            data = {"section_id": payload.section_id}
        elif request.action == "news_source_create":
            payload = NewsSourceCreatePayload.model_validate(request.payload or {})
            source_id = store.create_news_source(
                payload.section_id,
                payload.name,
                payload.source_type,
                payload.source_ref,
                payload.status,
            )
            data = {"source_id": source_id}
        elif request.action == "news_source_list":
            payload = NewsSourceListPayload.model_validate(request.payload or {})
            data = {
                "sources": store.list_news_sources(
                    payload.section_id,
                    payload.status,
                    payload.limit,
                    payload.offset,
                )
            }
        elif request.action == "news_source_update":
            payload = NewsSourceUpdatePayload.model_validate(request.payload or {})
            store.update_news_source(
                payload.source_id,
                payload.section_id,
                payload.name,
                payload.source_type,
                payload.source_ref,
                payload.status,
            )
            data = {"source_id": payload.source_id}
        elif request.action == "news_item_ingest":
            payload = NewsItemIngestPayload.model_validate(request.payload or {})
            data = store.ingest_news_item(
                payload.section_id,
                payload.source_id,
                payload.external_id,
                payload.title,
                payload.url,
                payload.published_at,
                payload.content_text,
                payload.raw_payload,
            )
        elif request.action == "news_item_summarize":
            payload = NewsItemSummarizePayload.model_validate(request.payload or {})
            data = summarize_news_item(
                store,
                payload.news_item_id,
                summary_format=payload.summary_format,
            )
        elif request.action == "news_briefing_generate":
            payload = NewsBriefingGeneratePayload.model_validate(request.payload or {})
            data = generate_manual_briefing(
                store,
                section_id=payload.section_id,
                source_id=payload.source_id,
                limit=payload.limit,
            )
        elif request.action == "news_briefing_get":
            payload = NewsBriefingGetPayload.model_validate(request.payload or {})
            if payload.briefing_id is None:
                data = store.get_latest_briefing()
            else:
                data = store.get_briefing(payload.briefing_id)
        elif request.action == "news_briefing_list":
            payload = NewsBriefingListPayload.model_validate(request.payload or {})
            data = {"briefings": store.list_briefings(payload.limit, payload.offset)}
        elif request.action == "news_item_save_to_db":
            payload = NewsItemSavePayload.model_validate(request.payload or {})
            item = store.get_news_item(payload.news_item_id)
            summary = store.get_news_item_summary(payload.news_item_id)
            if summary is None:
                summary = summarize_news_item(
                    store,
                    payload.news_item_id,
                    summary_format="plain",
                )
            title = payload.note_title or item.get("title") or f"News item {item['id']}"
            source_ref = item.get("url") or f"news_item:{item['id']}"
            note_id = store.create_note(
                title=title,
                body=summary["summary_text"],
                source_type="news_item",
                source_ref=source_ref,
            )
            data = {"note_id": note_id}
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
