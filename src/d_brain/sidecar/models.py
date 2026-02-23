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
