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
