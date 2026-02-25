"""Transport-agnostic memory ingestion for OpenClaw-first runtime paths."""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal
from uuid import uuid4

from d_brain.config import Settings, get_settings
from d_brain.services.session import SessionStore
from d_brain.services.storage import VaultStorage

logger = logging.getLogger(__name__)

SourceType = Literal["text", "voice", "command", "job", "system"]
Importance = Literal["low", "normal", "high"]
IndexState = Literal["true", "false", "deferred"]
Indexer = Callable[[dict[str, Any]], bool]

_WHITESPACE_RE = re.compile(r"\s+")


@dataclass(slots=True)
class IngestionRecord:
    source_type: SourceType
    user_id: str = ""
    channel: str = "system"
    source_ref: str = ""
    text: str = ""
    language: str = ""
    tags: list[str] | None = None
    created_at: str = ""
    importance: Importance = "normal"
    needs_indexing: bool = False
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_type": self.source_type,
            "user_id": self.user_id,
            "channel": self.channel,
            "source_ref": self.source_ref,
            "text": self.text,
            "language": self.language,
            "tags": list(self.tags or []),
            "created_at": self.created_at,
            "importance": self.importance,
            "needs_indexing": self.needs_indexing,
            "metadata": dict(self.metadata or {}),
        }


@dataclass(slots=True)
class IngestionResult:
    ok: bool
    stored: bool
    indexed: IndexState
    storage_targets: list[str]
    record_id: str
    skipped_reason: str = ""
    error: str = ""
    metrics: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "stored": self.stored,
            "indexed": self.indexed,
            "storage_targets": list(self.storage_targets),
            "record_id": self.record_id,
            "skipped_reason": self.skipped_reason,
            "error": self.error,
            "metrics": dict(self.metrics or {}),
        }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sanitize_text(value: str) -> str:
    cleaned = _WHITESPACE_RE.sub(" ", (value or "").strip())
    return cleaned[:8000]


def _coerce_record(raw: dict[str, Any]) -> IngestionRecord:
    source_type_raw = str(raw.get("source_type") or "system").strip().lower()
    source_type: SourceType = "system"
    if source_type_raw in {"text", "voice", "command", "job", "system"}:
        source_type = source_type_raw  # type: ignore[assignment]
    importance_raw = str(raw.get("importance") or "normal").strip().lower()
    importance: Importance = "normal"
    if importance_raw in {"low", "normal", "high"}:
        importance = importance_raw  # type: ignore[assignment]
    tags_raw = raw.get("tags")
    tags = [str(item).strip() for item in (tags_raw or []) if str(item).strip()]
    created_at = str(raw.get("created_at") or "").strip() or _now_iso()
    return IngestionRecord(
        source_type=source_type,
        user_id=str(raw.get("user_id") or "").strip(),
        channel=str(raw.get("channel") or "system").strip() or "system",
        source_ref=str(raw.get("source_ref") or "").strip(),
        text=_sanitize_text(str(raw.get("text") or raw.get("content") or "")),
        language=str(raw.get("language") or "").strip().lower(),
        tags=tags,
        created_at=created_at,
        importance=importance,
        needs_indexing=bool(raw.get("needs_indexing", False)),
        metadata=dict(raw.get("metadata") or {}),
    )


def _safe_dt(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now()


def _session_user_id(value: str) -> int | None:
    if not value:
        return None
    if value.isdigit():
        return int(value)
    return None


def _append_index_queue(settings: Settings, payload: dict[str, Any]) -> bool:
    queue_path = settings.vault_path / ".index_queue.jsonl"
    try:
        queue_path.parent.mkdir(parents=True, exist_ok=True)
        with queue_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        return True
    except OSError:
        return False


def ingest_record(
    record: dict[str, Any] | IngestionRecord,
    *,
    settings: Settings | None = None,
    indexer: Indexer | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    active_settings = settings or get_settings()
    record_obj = record if isinstance(record, IngestionRecord) else _coerce_record(record)
    record_id = uuid4().hex
    if not record_obj.text:
        duration_ms = int((time.perf_counter() - started) * 1000)
        return IngestionResult(
            ok=True,
            stored=False,
            indexed="false",
            storage_targets=[],
            record_id=record_id,
            skipped_reason="empty_content",
            metrics={"chars": 0, "duration_ms": duration_ms},
        ).to_dict()

    storage_targets: list[str] = []
    indexed: IndexState = "false"
    error = ""
    stored = False
    try:
        storage = VaultStorage(active_settings.vault_path)
        session = SessionStore(active_settings.vault_path)
        ts = _safe_dt(record_obj.created_at)
        tags = ",".join(record_obj.tags or [])
        header = f"[{record_obj.source_type}]"
        if tags:
            header = f"{header}[tags:{tags}]"
        if record_obj.source_ref:
            header = f"{header}[source:{record_obj.source_ref}]"
        storage.append_to_daily(record_obj.text, ts, header)
        storage_targets.append("vault.daily")
        session_user = _session_user_id(record_obj.user_id)
        if session_user is not None:
            session.append(
                session_user,
                "memory_ingest",
                source_type=record_obj.source_type,
                channel=record_obj.channel,
                source_ref=record_obj.source_ref,
                language=record_obj.language,
                importance=record_obj.importance,
                text=record_obj.text,
                tags=list(record_obj.tags or []),
                metadata=dict(record_obj.metadata or {}),
                record_id=record_id,
            )
            storage_targets.append("session.jsonl")
        stored = True
    except Exception as exc:
        error = f"storage_error:{exc}"
        logger.warning("Memory ingest storage failure: source_type=%s error=%s", record_obj.source_type, str(exc))

    if record_obj.needs_indexing:
        payload = {"record_id": record_id, **record_obj.to_dict()}
        if indexer is not None:
            try:
                indexed_ok = bool(indexer(payload))
                indexed = "true" if indexed_ok else "deferred"
            except Exception as exc:
                indexed = "deferred"
                if not error:
                    error = f"indexer_unavailable:{exc}"
                logger.info("Memory ingest indexer unavailable: record_id=%s error=%s", record_id, str(exc))
        else:
            indexed = "deferred"
        if indexed == "deferred":
            queued = _append_index_queue(active_settings, payload)
            if queued:
                storage_targets.append("index.queue")
            if not queued and not error:
                error = "index_queue_unavailable"

    duration_ms = int((time.perf_counter() - started) * 1000)
    result = IngestionResult(
        ok=stored or (not stored and not error),
        stored=stored,
        indexed=indexed,
        storage_targets=storage_targets,
        record_id=record_id,
        skipped_reason="" if stored else "storage_unavailable",
        error=error,
        metrics={"chars": len(record_obj.text), "duration_ms": duration_ms},
    ).to_dict()
    logger.info(
        "Memory ingest: ok=%s stored=%s indexed=%s source_type=%s channel=%s source_ref=%s duration_ms=%s",
        bool(result.get("ok")),
        bool(result.get("stored")),
        result.get("indexed"),
        record_obj.source_type,
        record_obj.channel,
        record_obj.source_ref,
        duration_ms,
    )
    return result


def ingest_message_event(
    payload: dict[str, Any],
    *,
    settings: Settings | None = None,
    indexer: Indexer | None = None,
) -> dict[str, Any]:
    normalized = {
        "source_type": payload.get("source_type") or "text",
        "user_id": payload.get("user_id") or "",
        "channel": payload.get("channel") or "openclaw",
        "source_ref": payload.get("source_ref") or "",
        "text": payload.get("text") or payload.get("content") or "",
        "language": payload.get("language") or "",
        "tags": payload.get("tags") or [],
        "created_at": payload.get("created_at") or "",
        "importance": payload.get("importance") or "normal",
        "needs_indexing": bool(payload.get("needs_indexing", False)),
        "metadata": payload.get("metadata") or {},
    }
    return ingest_record(normalized, settings=settings, indexer=indexer)


def ingest_job_result(
    payload: dict[str, Any],
    *,
    settings: Settings | None = None,
    indexer: Indexer | None = None,
) -> dict[str, Any]:
    job_type = str(payload.get("job_type") or "job")
    status = "ok" if bool(payload.get("ok")) else "failed"
    executed = bool(payload.get("executed"))
    skipped_reason = str(payload.get("skipped_reason") or "")
    summary = f"job={job_type} status={status} executed={executed}"
    if skipped_reason:
        summary = f"{summary} skipped_reason={skipped_reason}"
    outbound = payload.get("outbound_result") or {}
    delivery_state = str(outbound.get("delivery_state") or "")
    if delivery_state:
        summary = f"{summary} delivery={delivery_state}"
    error = str(payload.get("error") or "")
    if error:
        summary = f"{summary} error={error[:180]}"
    normalized = {
        "source_type": "job",
        "user_id": str(payload.get("user_id") or ""),
        "channel": payload.get("channel") or "system",
        "source_ref": payload.get("source_ref") or "openclaw_jobs",
        "text": summary,
        "language": "en",
        "tags": ["job", job_type],
        "importance": "low",
        "needs_indexing": bool(payload.get("needs_indexing", True)),
        "metadata": {"raw_job_result": payload},
    }
    return ingest_record(normalized, settings=settings, indexer=indexer)

