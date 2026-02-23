"""Ingestion pipeline for sidecar."""

from __future__ import annotations

from typing import Any

from .errors import SidecarError
from .models import IngestPayload, SummaryResult
from .store import SQLiteStore
from .summarizer import HeuristicSummarizer


def extract_summary_input(payload: IngestPayload) -> str:
    """Extract text to summarize without persisting raw content."""
    if payload.content:
        return payload.content
    if payload.metadata and isinstance(payload.metadata, dict):
        transcript = payload.metadata.get("transcript")
        if isinstance(transcript, str) and transcript.strip():
            return transcript
    if payload.content_type != "text":
        raise SidecarError(
            "unsupported_type",
            "Non-text content requires a transcript in metadata.",
        )
    raise SidecarError("summary_error", "No text available for summarization.")


def run_summary_pipeline(
    payload: IngestPayload,
    summarizer: HeuristicSummarizer,
) -> SummaryResult:
    summary_input = extract_summary_input(payload)
    return summarizer.summarize(summary_input, payload.summary_format)


def ingest_payload(
    payload: IngestPayload,
    store: SQLiteStore,
    summarizer: HeuristicSummarizer | None = None,
) -> dict[str, Any]:
    """Persist artifact + summary and return response data."""
    active_summarizer = summarizer or HeuristicSummarizer()
    summary = run_summary_pipeline(payload, active_summarizer)
    artifact_id = store.create_artifact(payload)
    summary_id = store.create_summary(
        artifact_id=artifact_id,
        summary_text=summary.summary_text,
        summary_format=summary.summary_format,
        model_ref=summary.model_ref,
    )
    return {
        "artifact_id": artifact_id,
        "summary_id": summary_id,
        "summary_text": summary.summary_text,
        "summary_format": summary.summary_format,
        "model_ref": summary.model_ref,
    }
