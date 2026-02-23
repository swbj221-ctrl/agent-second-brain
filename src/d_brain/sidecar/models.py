"""Pydantic models for sidecar requests and ingestion."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class SidecarRequest(BaseModel):
    """Skill -> sidecar request envelope."""

    request_id: str = Field(..., min_length=1)
    user_id: str = Field(..., min_length=1)
    action: str = Field(..., min_length=1)
    payload: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


class SidecarErrorData(BaseModel):
    """Error payload for sidecar responses."""

    code: str
    message: str


class SidecarResponse(BaseModel):
    """Sidecar -> skill response envelope."""

    request_id: str
    status: Literal["ok", "error"]
    data: dict[str, Any] | None = None
    error: SidecarErrorData | None = None


class IngestPayload(BaseModel):
    """Payload for ingestion requests."""

    source_type: str = Field(..., min_length=1)
    content_type: Literal["text", "audio", "image", "file"]
    summary_format: str = Field(default="plain", min_length=1)
    external_id: str | None = None
    source_ref: str | None = None
    content: str | None = None
    content_path: str | None = None
    content_hash: str | None = None
    metadata: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_content(self) -> "IngestPayload":
        has_content = self.content is not None
        has_path = self.content_path is not None
        if has_content == has_path:
            raise ValueError("Provide exactly one of content or content_path.")
        if has_content and self.content_type != "text":
            raise ValueError("Inline content is only allowed for content_type=text.")
        if not has_content and self.content_type == "text":
            return self
        if not has_path and self.content_type != "text":
            raise ValueError("content_path is required for non-text content.")
        return self


class SummaryResult(BaseModel):
    """Result of summary generation."""

    summary_text: str
    summary_format: str
    model_ref: str


EventStatus = Literal["planned", "done", "canceled"]
ReminderStatus = Literal["pending", "triggered", "canceled"]
CalendarView = Literal["today", "upcoming", "date"]
ProjectStatus = Literal["active", "archived"]
TaskStatus = Literal["open", "done", "canceled"]


class EventCreatePayload(BaseModel):
    """Payload for creating a new event and reminder."""

    title: str = Field(..., min_length=1)
    body: str | None = None
    start_at: str | None = None
    end_at: str | None = None
    remind_at: str | None = None
    source_type: str | None = None
    source_ref: str | None = None


class EventListPayload(BaseModel):
    """Payload for listing events."""

    status: EventStatus | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class EventUpdateStatusPayload(BaseModel):
    """Payload for updating event status."""

    event_id: int = Field(..., ge=1)
    status: EventStatus


class ReminderListPayload(BaseModel):
    """Payload for listing reminders."""

    status: ReminderStatus | None = None
    due_before: str | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class ReminderUpdateStatusPayload(BaseModel):
    """Payload for updating reminder status."""

    reminder_id: int = Field(..., ge=1)
    status: ReminderStatus


class ReminderDeliveryRunPayload(BaseModel):
    """Payload for running reminder delivery."""

    chat_id: int = Field(..., ge=1)
    mode: Literal["manual", "scheduler"] = "manual"


class CalendarViewPayload(BaseModel):
    """Payload for calendar-style reminder views."""

    view: CalendarView = "today"
    limit: int = Field(default=10, ge=1, le=200)
    date: str | None = None

    @model_validator(mode="after")
    def validate_date(self) -> "CalendarViewPayload":
        if self.view == "date" and not (self.date and self.date.strip()):
            raise ValueError("date is required for view=date.")
        return self


class ProjectCreatePayload(BaseModel):
    """Payload for creating a project."""

    name: str = Field(..., min_length=1)


class ProjectListPayload(BaseModel):
    """Payload for listing projects."""

    status: ProjectStatus | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class ProjectUpdateStatusPayload(BaseModel):
    """Payload for updating project status."""

    project_id: int = Field(..., ge=1)
    status: ProjectStatus


class ProjectGetPayload(BaseModel):
    """Payload for retrieving a project."""

    project_id: int = Field(..., ge=1)


class TaskCreatePayload(BaseModel):
    """Payload for creating a task."""

    project_id: int = Field(..., ge=1)
    title: str = Field(..., min_length=1)
    status: TaskStatus = "open"
    due_at: str | None = None
    source_type: str | None = None
    source_ref: str | None = None


class TaskListPayload(BaseModel):
    """Payload for listing tasks."""

    project_id: int | None = Field(default=None, ge=1)
    status: TaskStatus | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class TaskUpdateStatusPayload(BaseModel):
    """Payload for updating task status."""

    task_id: int = Field(..., ge=1)
    status: TaskStatus


class TaskUpdateProjectPayload(BaseModel):
    """Payload for moving a task to another project."""

    task_id: int = Field(..., ge=1)
    project_id: int = Field(..., ge=1)


class TaskNoteAddPayload(BaseModel):
    """Payload for adding a task note."""

    task_id: int = Field(..., ge=1)
    text: str = Field(..., min_length=1)


class TaskGetPayload(BaseModel):
    """Payload for retrieving a task."""

    task_id: int = Field(..., ge=1)


class EventParsePayload(BaseModel):
    """Payload for rule-first event parsing."""

    text: str = Field(..., min_length=1)
    source_type: str | None = None
    source_ref: str | None = None


class EnglishWordAddPayload(BaseModel):
    """Payload for adding an English word."""

    word: str = Field(..., min_length=1)


class EnglishWordListPayload(BaseModel):
    """Payload for listing English words."""

    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class EnglishTopicAddPayload(BaseModel):
    """Payload for adding an English topic."""

    name: str = Field(..., min_length=1)


class EnglishTopicListPayload(BaseModel):
    """Payload for listing English topics."""

    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class EnglishSessionCreatePayload(BaseModel):
    """Payload for creating an English session."""

    topic_id: int | None = Field(default=None, ge=1)


EnglishSessionRole = Literal["user", "assistant", "system"]


class EnglishSessionTurnAppendPayload(BaseModel):
    """Payload for appending a session turn."""

    session_id: int = Field(..., ge=1)
    role: EnglishSessionRole
    content: str = Field(..., min_length=1)


class EnglishSessionClosePayload(BaseModel):
    """Payload for closing an English session."""

    session_id: int = Field(..., ge=1)
    summary_text: str | None = None


ReflectionSessionRole = Literal["user", "assistant", "system"]


class ReflectionSessionCreatePayload(BaseModel):
    """Payload for creating a reflection session."""

    pass


class ReflectionSessionTurnAppendPayload(BaseModel):
    """Payload for appending a reflection session turn."""

    session_id: int = Field(..., ge=1)
    role: ReflectionSessionRole
    content: str = Field(..., min_length=1)


class ReflectionSessionClosePayload(BaseModel):
    """Payload for closing a reflection session."""

    session_id: int = Field(..., ge=1)
    summary_text: str | None = None


class ReflectionSessionListPayload(BaseModel):
    """Payload for listing reflection sessions."""

    status: Literal["open", "closed"] | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class BooksAddPayload(BaseModel):
    """Payload for adding a book entry."""

    content: str = Field(..., min_length=1)
    source_ref: str | None = None


class BooksListPayload(BaseModel):
    """Payload for listing book entries."""

    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class PhilosophyAddPayload(BaseModel):
    """Payload for adding a philosophy entry."""

    content: str = Field(..., min_length=1)
    source_ref: str | None = None


class PhilosophyListPayload(BaseModel):
    """Payload for listing philosophy entries."""

    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class KnowledgeInboxAddPayload(BaseModel):
    """Payload for adding a knowledge inbox item."""

    content: str = Field(..., min_length=1)
    summary_format: str = Field(default="plain", min_length=1)
    source_ref: str | None = None
    external_id: str | None = None


class KnowledgeInboxListPayload(BaseModel):
    """Payload for listing knowledge inbox items."""

    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class KnowledgeItemSummarizePayload(BaseModel):
    """Payload for retrieving a knowledge item summary."""

    artifact_id: int = Field(..., ge=1)


class KnowledgeItemSavePayload(BaseModel):
    """Payload for saving a knowledge item to notes."""

    artifact_id: int = Field(..., ge=1)
    note_title: str | None = None


class HealthRecordAddPayload(BaseModel):
    """Payload for adding a generic health record."""

    title: str = Field(..., min_length=1)
    record_type: str | None = None
    notes: str | None = None
    occurred_at: str | None = None
    source_type: str | None = None
    source_ref: str | None = None


class HealthRecordListPayload(BaseModel):
    """Payload for listing health records."""

    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class HealthMedicationAddPayload(BaseModel):
    """Payload for adding a health medication."""

    name: str = Field(..., min_length=1)
    dosage: str | None = None
    schedule: str | None = None
    started_at: str | None = None
    ended_at: str | None = None
    notes: str | None = None


class HealthMedicationListPayload(BaseModel):
    """Payload for listing health medications."""

    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class HealthTreatmentAddPayload(BaseModel):
    """Payload for adding a health treatment."""

    name: str = Field(..., min_length=1)
    description: str | None = None
    started_at: str | None = None
    ended_at: str | None = None
    notes: str | None = None


class HealthTreatmentListPayload(BaseModel):
    """Payload for listing health treatments."""

    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class HealthObservationAddPayload(BaseModel):
    """Payload for adding a health observation."""

    observation_type: str = Field(..., min_length=1)
    value: str | None = None
    unit: str | None = None
    observed_at: str | None = None
    notes: str | None = None


class HealthObservationListPayload(BaseModel):
    """Payload for listing health observations."""

    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class HealthLabReportAddPayload(BaseModel):
    """Payload for linking a lab report artifact."""

    artifact_id: int = Field(..., ge=1)
    title: str | None = None
    report_date: str | None = None
    notes: str | None = None


class HealthLabReportListPayload(BaseModel):
    """Payload for listing lab report links."""

    artifact_id: int | None = Field(default=None, ge=1)
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class HeartbeatTickPayload(BaseModel):
    """Payload for recording a heartbeat log entry."""

    event_type: str = Field(default="heartbeat_tick", min_length=1)
    event_source: str | None = None
    event_details: dict[str, Any] | None = None


class DigestGeneratePayload(BaseModel):
    """Payload for generating a system-state digest."""

    digest_type: Literal["system_state"] = "system_state"


class DigestGetLatestPayload(BaseModel):
    """Payload for retrieving the latest digest."""

    pass


class DigestListPayload(BaseModel):
    """Payload for listing digests."""

    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


NewsSectionStatus = Literal["active", "inactive"]
NewsSourceStatus = Literal["active", "inactive"]


class NewsSectionCreatePayload(BaseModel):
    """Payload for creating a news section."""

    name: str = Field(..., min_length=1)
    description: str | None = None
    status: NewsSectionStatus = "active"


class NewsSectionListPayload(BaseModel):
    """Payload for listing news sections."""

    status: NewsSectionStatus | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class NewsSectionUpdatePayload(BaseModel):
    """Payload for updating a news section."""

    section_id: int = Field(..., ge=1)
    name: str | None = None
    description: str | None = None
    status: NewsSectionStatus | None = None

    @model_validator(mode="after")
    def validate_updates(self) -> "NewsSectionUpdatePayload":
        if self.name is None and self.description is None and self.status is None:
            raise ValueError("Provide at least one field to update.")
        return self


class NewsSourceCreatePayload(BaseModel):
    """Payload for creating a news source."""

    section_id: int = Field(..., ge=1)
    name: str = Field(..., min_length=1)
    source_type: str = Field(..., min_length=1)
    source_ref: str | None = None
    status: NewsSourceStatus = "active"


class NewsSourceListPayload(BaseModel):
    """Payload for listing news sources."""

    section_id: int | None = Field(default=None, ge=1)
    status: NewsSourceStatus | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class NewsSourceUpdatePayload(BaseModel):
    """Payload for updating a news source."""

    source_id: int = Field(..., ge=1)
    section_id: int | None = Field(default=None, ge=1)
    name: str | None = None
    source_type: str | None = None
    source_ref: str | None = None
    status: NewsSourceStatus | None = None

    @model_validator(mode="after")
    def validate_updates(self) -> "NewsSourceUpdatePayload":
        if (
            self.section_id is None
            and self.name is None
            and self.source_type is None
            and self.source_ref is None
            and self.status is None
        ):
            raise ValueError("Provide at least one field to update.")
        return self


class NewsItemIngestPayload(BaseModel):
    """Payload for ingesting a news item."""

    section_id: int = Field(..., ge=1)
    source_id: int = Field(..., ge=1)
    external_id: str | None = None
    title: str | None = None
    url: str | None = None
    published_at: str | None = None
    content_text: str | None = None
    raw_payload: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_content(self) -> "NewsItemIngestPayload":
        if (
            self.external_id is None
            and self.title is None
            and self.url is None
            and self.content_text is None
            and self.raw_payload is None
        ):
            raise ValueError("Provide at least one content field for ingestion.")
        return self


class NewsItemSummarizePayload(BaseModel):
    """Payload for summarizing a news item."""

    news_item_id: int = Field(..., ge=1)
    summary_format: str = Field(default="plain", min_length=1)


class NewsBriefingGeneratePayload(BaseModel):
    """Payload for generating a manual news briefing."""

    section_id: int | None = Field(default=None, ge=1)
    source_id: int | None = Field(default=None, ge=1)
    limit: int = Field(default=50, ge=5, le=500)


class NewsBriefingGetPayload(BaseModel):
    """Payload for retrieving a briefing."""

    briefing_id: int | None = Field(default=None, ge=1)


class NewsBriefingListPayload(BaseModel):
    """Payload for listing briefings."""

    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class NewsItemSavePayload(BaseModel):
    """Payload for saving a news item to notes."""

    news_item_id: int = Field(..., ge=1)
    note_title: str | None = None


class CodexUsageLogAddPayload(BaseModel):
    """Payload for recording Codex usage metrics."""

    scope_key: str = Field(default="global", min_length=1)
    request_id: str | None = None
    user_id: str | None = None
    model_ref: str | None = None
    context: str | None = None
    tokens_in: int = Field(default=0, ge=0)
    tokens_out: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    latency_ms: int = Field(default=0, ge=0)
    request_count: int = Field(default=1, ge=1)
    metadata: dict[str, Any] | None = None


class CodexUsageStatusGetPayload(BaseModel):
    """Payload for retrieving Codex usage status."""

    scope_key: str = Field(default="global", min_length=1)


class CodexLimitsSettingsUpsertPayload(BaseModel):
    """Payload for upserting Codex limits settings."""

    scope_key: str = Field(default="global", min_length=1)
    window_hours: int = Field(default=24, ge=1, le=720)
    max_tokens: int = Field(default=0, ge=0)
    max_requests: int = Field(default=0, ge=0)
    max_latency_ms: int = Field(default=0, ge=0)
    warn_ratio: float = Field(default=0.70, ge=0.0, le=1.0)
    critical_ratio: float = Field(default=0.90, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_ratios(self) -> "CodexLimitsSettingsUpsertPayload":
        if self.critical_ratio < self.warn_ratio:
            raise ValueError("critical_ratio must be >= warn_ratio.")
        return self


class CodexLimitsSettingsGetPayload(BaseModel):
    """Payload for retrieving Codex limits settings."""

    scope_key: str = Field(default="global", min_length=1)


class CodexUsageListPayload(BaseModel):
    """Payload for listing recent Codex usage logs."""

    scope_key: str = Field(default="global", min_length=1)
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


IdeaResearchJobStatus = Literal["active", "archived"]
IdeaResearchRunStatus = Literal["started", "completed", "failed"]


class IdeaResearchJobCreatePayload(BaseModel):
    """Payload for creating an idea research job."""

    title: str = Field(..., min_length=1)
    status: IdeaResearchJobStatus = "active"
    notes: str | None = None


class IdeaResearchJobListPayload(BaseModel):
    """Payload for listing idea research jobs."""

    status: IdeaResearchJobStatus | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class IdeaResearchJobUpdatePayload(BaseModel):
    """Payload for updating an idea research job."""

    job_id: int = Field(..., ge=1)
    title: str | None = None
    status: IdeaResearchJobStatus | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def validate_updates(self) -> "IdeaResearchJobUpdatePayload":
        if self.title is None and self.status is None and self.notes is None:
            raise ValueError("Provide at least one field to update.")
        return self


class IdeaResearchRunStartPayload(BaseModel):
    """Payload for starting a manual idea research run."""

    job_id: int = Field(..., ge=1)
    finding_types: list[str] | None = None
    summary_text: str | None = None


class IdeaResearchRunGetPayload(BaseModel):
    """Payload for retrieving an idea research run."""

    run_id: int = Field(..., ge=1)


class IdeaResearchReportGetPayload(BaseModel):
    """Payload for retrieving an idea research report."""

    report_id: int | None = Field(default=None, ge=1)
    run_id: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_selector(self) -> "IdeaResearchReportGetPayload":
        if self.report_id is None and self.run_id is None:
            raise ValueError("Provide report_id or run_id.")
        return self
