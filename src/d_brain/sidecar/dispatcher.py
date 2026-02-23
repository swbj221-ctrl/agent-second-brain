"""Sidecar request dispatcher for Stage 2 ingestion."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError

from d_brain.config import Settings, get_settings

from .errors import (
    INTERNAL_ERROR_CODE,
    INTERNAL_ERROR_MESSAGE,
    SidecarError,
)
from .ingestion import ingest_payload
from .idea_research import (
    get_research_report,
    get_research_run,
    start_manual_research_run,
)
from .models import (
    EnglishSessionClosePayload,
    EnglishSessionCreatePayload,
    EnglishSessionTurnAppendPayload,
    EnglishTopicAddPayload,
    EnglishTopicListPayload,
    EnglishWordAddPayload,
    EnglishWordListPayload,
    BooksAddPayload,
    BooksListPayload,
    PhilosophyAddPayload,
    PhilosophyListPayload,
    KnowledgeInboxAddPayload,
    KnowledgeInboxListPayload,
    KnowledgeItemSummarizePayload,
    KnowledgeItemSavePayload,
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
    ProjectCreatePayload,
    ProjectGetPayload,
    ProjectListPayload,
    ProjectUpdateStatusPayload,
    TaskCreatePayload,
    TaskGetPayload,
    TaskListPayload,
    TaskNoteAddPayload,
    TaskUpdateProjectPayload,
    TaskUpdateStatusPayload,
    HealthLabReportAddPayload,
    HealthLabReportListPayload,
    HealthMedicationAddPayload,
    HealthMedicationListPayload,
    HealthObservationAddPayload,
    HealthObservationListPayload,
    HealthRecordAddPayload,
    HealthRecordListPayload,
    HealthTreatmentAddPayload,
    HealthTreatmentListPayload,
    HeartbeatTickPayload,
    IdeaResearchJobCreatePayload,
    IdeaResearchJobListPayload,
    IdeaResearchJobUpdatePayload,
    IdeaResearchReportGetPayload,
    IdeaResearchRunGetPayload,
    IdeaResearchRunStartPayload,
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
    ReminderDeliveryRunPayload,
    ReminderListPayload,
    ReminderUpdateStatusPayload,
    CalendarViewPayload,
    SidecarErrorData,
    SidecarRequest,
    SidecarResponse,
)
from .jobs import deliver_due_reminders
from .plans import (
    create_event_with_default_reminder,
    parse_event_text,
    trigger_due_reminders,
    update_event_status,
    update_reminder_status,
)
from .news import generate_manual_briefing, summarize_news_item
from .store import SQLiteStore, utc_now


def payload_size_bytes(payload: dict[str, Any]) -> int:
    """Calculate JSON-encoded payload size in bytes."""
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=True)
    return len(raw.encode("utf-8"))


def make_note_title(content: str, max_len: int = 80) -> str:
    cleaned = " ".join(content.strip().split())
    if len(cleaned) <= max_len:
        return cleaned
    return f"{cleaned[: max_len - 3]}..."


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
    logger = logging.getLogger(__name__)
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
        elif request.action == "books_add":
            payload = BooksAddPayload.model_validate(request.payload or {})
            content = payload.content.strip()
            title = make_note_title(content)
            note_id = store.create_note(
                title=title,
                body=content,
                source_type="books",
                source_ref=payload.source_ref,
            )
            store.add_note_category(note_id, "books")
            data = {"note_id": note_id}
        elif request.action == "books_list":
            payload = BooksListPayload.model_validate(request.payload or {})
            data = {
                "books": store.list_notes_by_category(
                    "books",
                    payload.limit,
                    payload.offset,
                )
            }
        elif request.action == "philosophy_add":
            payload = PhilosophyAddPayload.model_validate(request.payload or {})
            content = payload.content.strip()
            title = make_note_title(content)
            note_id = store.create_note(
                title=title,
                body=content,
                source_type="philosophy",
                source_ref=payload.source_ref,
            )
            store.add_note_category(note_id, "philosophy")
            data = {"note_id": note_id}
        elif request.action == "philosophy_list":
            payload = PhilosophyListPayload.model_validate(request.payload or {})
            data = {
                "items": store.list_notes_by_category(
                    "philosophy",
                    payload.limit,
                    payload.offset,
                )
            }
        elif request.action == "knowledge_inbox_add":
            payload = KnowledgeInboxAddPayload.model_validate(request.payload or {})
            ingest = IngestPayload(
                source_type="knowledge_inbox",
                content_type="text",
                summary_format=payload.summary_format,
                external_id=payload.external_id,
                source_ref=payload.source_ref,
                content=payload.content,
            )
            data = ingest_payload(ingest, store)
        elif request.action == "knowledge_inbox_list":
            payload = KnowledgeInboxListPayload.model_validate(request.payload or {})
            data = {
                "items": store.list_artifacts_by_source_type(
                    "knowledge_inbox",
                    payload.limit,
                    payload.offset,
                )
            }
        elif request.action == "knowledge_item_summarize":
            payload = KnowledgeItemSummarizePayload.model_validate(request.payload or {})
            summary = store.get_artifact_summary(payload.artifact_id)
            if summary is None:
                raise SidecarError(
                    "not_found",
                    f"No summary found for artifact {payload.artifact_id}.",
                )
            data = {
                "artifact_id": payload.artifact_id,
                "summary_id": summary["id"],
                "summary_text": summary["summary_text"],
                "summary_format": summary["summary_format"],
                "model_ref": summary["model_ref"],
            }
        elif request.action == "knowledge_item_save_to_db":
            payload = KnowledgeItemSavePayload.model_validate(request.payload or {})
            artifact = store.get_artifact(payload.artifact_id)
            summary = store.get_artifact_summary(payload.artifact_id)
            if summary is None:
                raise SidecarError(
                    "not_found",
                    f"No summary found for artifact {payload.artifact_id}.",
                )
            title = payload.note_title or f"Knowledge item {payload.artifact_id}"
            source_ref = artifact.get("source_ref") or f"artifact:{payload.artifact_id}"
            note_id = store.create_note(
                title=title,
                body=summary["summary_text"],
                source_type="knowledge_inbox",
                source_ref=source_ref,
            )
            store.add_note_category(note_id, "knowledge")
            data = {"note_id": note_id}
        elif request.action == "health_record_add":
            payload = HealthRecordAddPayload.model_validate(request.payload or {})
            record_id = store.create_health_record(
                title=payload.title,
                record_type=payload.record_type,
                notes=payload.notes,
                occurred_at=payload.occurred_at,
                source_type=payload.source_type,
                source_ref=payload.source_ref,
            )
            data = {"record_id": record_id}
        elif request.action == "health_record_list":
            payload = HealthRecordListPayload.model_validate(request.payload or {})
            data = {"records": store.list_health_records(payload.limit, payload.offset)}
        elif request.action == "health_medication_add":
            payload = HealthMedicationAddPayload.model_validate(request.payload or {})
            medication_id = store.create_health_medication(
                name=payload.name,
                dosage=payload.dosage,
                schedule=payload.schedule,
                started_at=payload.started_at,
                ended_at=payload.ended_at,
                notes=payload.notes,
            )
            data = {"medication_id": medication_id}
        elif request.action == "health_medication_list":
            payload = HealthMedicationListPayload.model_validate(request.payload or {})
            data = {
                "medications": store.list_health_medications(payload.limit, payload.offset)
            }
        elif request.action == "health_treatment_add":
            payload = HealthTreatmentAddPayload.model_validate(request.payload or {})
            treatment_id = store.create_health_treatment(
                name=payload.name,
                description=payload.description,
                started_at=payload.started_at,
                ended_at=payload.ended_at,
                notes=payload.notes,
            )
            data = {"treatment_id": treatment_id}
        elif request.action == "health_treatment_list":
            payload = HealthTreatmentListPayload.model_validate(request.payload or {})
            data = {"treatments": store.list_health_treatments(payload.limit, payload.offset)}
        elif request.action == "health_observation_add":
            payload = HealthObservationAddPayload.model_validate(request.payload or {})
            observation_id = store.create_health_observation(
                observation_type=payload.observation_type,
                value=payload.value,
                unit=payload.unit,
                observed_at=payload.observed_at,
                notes=payload.notes,
            )
            data = {"observation_id": observation_id}
        elif request.action == "health_observation_list":
            payload = HealthObservationListPayload.model_validate(request.payload or {})
            data = {
                "observations": store.list_health_observations(payload.limit, payload.offset)
            }
        elif request.action == "health_lab_report_add":
            payload = HealthLabReportAddPayload.model_validate(request.payload or {})
            report_id = store.create_health_lab_report(
                artifact_id=payload.artifact_id,
                title=payload.title,
                report_date=payload.report_date,
                notes=payload.notes,
            )
            data = {"lab_report_id": report_id}
        elif request.action == "health_lab_report_list":
            payload = HealthLabReportListPayload.model_validate(request.payload or {})
            data = {
                "lab_reports": store.list_health_lab_reports(
                    payload.artifact_id, payload.limit, payload.offset
                )
            }
        elif request.action == "idea_research_job_create":
            payload = IdeaResearchJobCreatePayload.model_validate(request.payload or {})
            job_id = store.create_idea_research_job(
                payload.title,
                payload.status,
                payload.notes,
            )
            data = {"job_id": job_id}
        elif request.action == "idea_research_job_list":
            payload = IdeaResearchJobListPayload.model_validate(request.payload or {})
            data = {
                "jobs": store.list_idea_research_jobs(
                    payload.status, payload.limit, payload.offset
                )
            }
        elif request.action == "idea_research_job_update":
            payload = IdeaResearchJobUpdatePayload.model_validate(request.payload or {})
            store.update_idea_research_job(
                payload.job_id,
                payload.title,
                payload.status,
                payload.notes,
            )
            data = {"job_id": payload.job_id}
        elif request.action == "idea_research_run_start":
            payload = IdeaResearchRunStartPayload.model_validate(request.payload or {})
            data = start_manual_research_run(
                store,
                job_id=payload.job_id,
                finding_types=payload.finding_types,
                summary_text=payload.summary_text,
            )
        elif request.action == "idea_research_run_get":
            payload = IdeaResearchRunGetPayload.model_validate(request.payload or {})
            data = get_research_run(store, payload.run_id)
        elif request.action == "idea_research_report_get":
            payload = IdeaResearchReportGetPayload.model_validate(request.payload or {})
            data = get_research_report(
                store,
                report_id=payload.report_id,
                run_id=payload.run_id,
            )
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
        elif request.action == "project_create":
            payload = ProjectCreatePayload.model_validate(request.payload or {})
            project_id = store.create_project(payload.name, "active")
            data = {"project_id": project_id}
        elif request.action == "project_list":
            payload = ProjectListPayload.model_validate(request.payload or {})
            data = {
                "projects": store.list_projects(payload.status, payload.limit, payload.offset)
            }
        elif request.action == "project_update_status":
            payload = ProjectUpdateStatusPayload.model_validate(request.payload or {})
            store.update_project_status(payload.project_id, payload.status)
            data = {"project_id": payload.project_id}
        elif request.action == "project_get":
            payload = ProjectGetPayload.model_validate(request.payload or {})
            project = store.get_project(payload.project_id)
            if project is None:
                raise SidecarError(
                    "not_found",
                    f"Project {payload.project_id} not found.",
                )
            data = {"project": project}
        elif request.action == "task_create":
            payload = TaskCreatePayload.model_validate(request.payload or {})
            task_id = store.create_task(
                payload.project_id,
                payload.title,
                payload.status,
                payload.due_at,
                payload.source_type,
                payload.source_ref,
            )
            data = {"task_id": task_id}
        elif request.action == "task_list":
            payload = TaskListPayload.model_validate(request.payload or {})
            data = {
                "tasks": store.list_tasks(
                    payload.project_id,
                    payload.status,
                    payload.limit,
                    payload.offset,
                )
            }
        elif request.action == "task_update_status":
            payload = TaskUpdateStatusPayload.model_validate(request.payload or {})
            store.update_task_status(payload.task_id, payload.status)
            data = {"task_id": payload.task_id}
        elif request.action == "task_update_project":
            payload = TaskUpdateProjectPayload.model_validate(request.payload or {})
            store.update_task_project(payload.task_id, payload.project_id)
            data = {"task_id": payload.task_id, "project_id": payload.project_id}
        elif request.action == "task_note_add":
            payload = TaskNoteAddPayload.model_validate(request.payload or {})
            task = store.get_task(payload.task_id)
            if task is None:
                raise SidecarError("not_found", f"Task {payload.task_id} not found.")
            note_id = store.create_note(
                title=make_note_title(payload.text),
                body=payload.text,
                source_type="task",
                source_ref=str(payload.task_id),
            )
            data = {"note_id": note_id, "task_id": payload.task_id}
        elif request.action == "task_get":
            payload = TaskGetPayload.model_validate(request.payload or {})
            task = store.get_task(payload.task_id)
            if task is None:
                raise SidecarError("not_found", f"Task {payload.task_id} not found.")
            data = {"task": task}
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
        elif request.action == "reminder_delivery_run":
            payload = ReminderDeliveryRunPayload.model_validate(request.payload or {})
            data = deliver_due_reminders(
                store,
                active_settings,
                [payload.chat_id],
                mode=payload.mode,
            )
        elif request.action == "calendar_view":
            payload = CalendarViewPayload.model_validate(request.payload or {})
            date_value = None
            if payload.view == "today":
                date_value = datetime.now(timezone.utc).date().isoformat()
                items = store.list_reminders_for_date(
                    date_value,
                    "pending",
                    "planned",
                    payload.limit,
                    0,
                )
            elif payload.view == "date":
                date_value = (payload.date or "").strip()
                items = store.list_reminders_for_date(
                    date_value,
                    "pending",
                    "planned",
                    payload.limit,
                    0,
                )
            else:
                now_iso = utc_now()
                items = store.list_upcoming_reminders(
                    now_iso,
                    "pending",
                    "planned",
                    payload.limit,
                )
            data = {
                "view": payload.view,
                "date": date_value,
                "count": len(items),
                "items": items,
            }
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
        logger.info(
            "Sidecar error action=%s code=%s",
            raw_request.get("action"),
            exc.code,
        )
        response = SidecarResponse(
            request_id=raw_request.get("request_id", "unknown"),
            status="error",
            error=SidecarErrorData(code=exc.code, message=exc.message),
        )
    except ValidationError as exc:
        logger.info(
            "Sidecar validation error action=%s details=%s",
            raw_request.get("action"),
            exc.errors(),
        )
        response = SidecarResponse(
            request_id=raw_request.get("request_id", "unknown"),
            status="error",
            error=SidecarErrorData(code="invalid_payload", message=str(exc)),
        )
    except Exception:
        logger.exception(
            "Sidecar unexpected error action=%s request_id=%s",
            raw_request.get("action"),
            raw_request.get("request_id"),
        )
        response = SidecarResponse(
            request_id=raw_request.get("request_id", "unknown"),
            status="error",
            error=SidecarErrorData(
                code=INTERNAL_ERROR_CODE,
                message=INTERNAL_ERROR_MESSAGE,
            ),
        )
    return response.model_dump()
