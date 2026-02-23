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
