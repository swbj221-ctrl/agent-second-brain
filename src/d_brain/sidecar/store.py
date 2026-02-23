"""SQLite storage helpers for sidecar ingestion."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .errors import SidecarError
from .models import IngestPayload


def utc_now() -> str:
    """Return UTC timestamp in ISO format (seconds precision)."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def compute_hash(text: str) -> str:
    """Compute a sha256 hash for text content."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalize_whitespace(value: str) -> str:
    """Trim and collapse internal whitespace."""
    return " ".join(value.strip().split())


def normalize_news_text(value: str | None, lower: bool = False) -> str | None:
    """Normalize text for deterministic hashing."""
    if value is None:
        return None
    cleaned = normalize_whitespace(value)
    return cleaned.lower() if lower else cleaned


def normalize_news_hash_payload(
    title: str | None,
    url: str | None,
    published_at: str | None,
    content_text: str | None,
    external_id: str | None,
    raw_payload: dict[str, Any] | None,
) -> str:
    """Normalize news item fields into a deterministic hash input."""
    payload = {
        "title": normalize_news_text(title, lower=True),
        "url": normalize_news_text(url, lower=True),
        "published_at": normalize_news_text(published_at, lower=False),
        "content_text": normalize_news_text(content_text, lower=True),
        "external_id": normalize_news_text(external_id, lower=False),
        "raw_payload": raw_payload,
    }
    normalized = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return compute_hash(normalized)


def dumps_json(payload: dict[str, Any] | None) -> str | None:
    if payload is None:
        return None
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


@dataclass(slots=True)
class SQLiteStore:
    """SQLite-backed storage for artifacts and summaries."""

    db_path: Path

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def _count_table(self, conn: sqlite3.Connection, table: str, where: str = "", params: tuple[Any, ...] = ()) -> int:
        query = f"SELECT COUNT(*) FROM {table}"
        if where:
            query += f" WHERE {where}"
        row = conn.execute(query, params).fetchone()
        return int(row[0]) if row else 0

    def _max_timestamp(
        self,
        conn: sqlite3.Connection,
        table: str,
        column: str = "created_at",
        where: str = "",
        params: tuple[Any, ...] = (),
    ) -> str | None:
        query = f"SELECT MAX({column}) FROM {table}"
        if where:
            query += f" WHERE {where}"
        row = conn.execute(query, params).fetchone()
        if not row:
            return None
        return row[0]

    def create_heartbeat_log(
        self,
        event_type: str,
        event_source: str | None,
        event_details: dict[str, Any] | None,
    ) -> dict[str, Any]:
        timestamp = utc_now()
        details_json = dumps_json(event_details)
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO heartbeat_logs (
                    event_type,
                    event_source,
                    event_details,
                    created_at
                )
                VALUES (?, ?, ?, ?);
                """,
                (event_type, event_source, details_json, timestamp),
            )
            log_id = int(cursor.lastrowid)
        return {
            "heartbeat_log_id": log_id,
            "event_type": event_type,
            "event_source": event_source,
            "created_at": timestamp,
        }

    def create_digest(self, digest_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        timestamp = utc_now()
        payload_json = dumps_json(payload)
        if payload_json is None:
            raise SidecarError("invalid_payload", "Digest payload is required.")
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO digests (
                    digest_type,
                    payload,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?);
                """,
                (digest_type, payload_json, timestamp, timestamp),
            )
            digest_id = int(cursor.lastrowid)
        return {
            "digest_id": digest_id,
            "digest_type": digest_type,
            "payload": payload,
            "created_at": timestamp,
            "updated_at": timestamp,
        }

    def get_latest_digest(self) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, digest_type, payload, created_at, updated_at
                FROM digests
                ORDER BY id DESC
                LIMIT 1;
                """,
            ).fetchone()
        if not row:
            raise SidecarError("not_found", "No digests found.")
        payload = json.loads(row[2]) if row[2] else {}
        return {
            "id": row[0],
            "digest_type": row[1],
            "payload": payload,
            "created_at": row[3],
            "updated_at": row[4],
        }

    def list_digests(self, limit: int, offset: int) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, digest_type, created_at, updated_at
                FROM digests
                ORDER BY id DESC
                LIMIT ? OFFSET ?;
                """,
                (limit, offset),
            ).fetchall()
        return [
            {
                "id": row[0],
                "digest_type": row[1],
                "created_at": row[2],
                "updated_at": row[3],
            }
            for row in rows
        ]

    def generate_system_state_digest(self) -> dict[str, Any]:
        timestamp = utc_now()
        with self._connect() as conn:
            counts = {
                "artifacts": self._count_table(conn, "artifacts"),
                "artifact_summaries": self._count_table(conn, "artifact_summaries"),
                "notes": self._count_table(conn, "notes"),
                "events": self._count_table(conn, "events"),
                "event_reminders": self._count_table(conn, "event_reminders"),
                "english_words": self._count_table(conn, "english_words"),
                "english_topics": self._count_table(conn, "english_topics"),
                "english_sessions_open": self._count_table(
                    conn, "english_sessions", "status = ?", ("open",)
                ),
                "english_sessions_closed": self._count_table(
                    conn, "english_sessions", "status = ?", ("closed",)
                ),
                "reflection_sessions_open": self._count_table(
                    conn, "reflection_sessions", "status = ?", ("open",)
                ),
                "reflection_sessions_closed": self._count_table(
                    conn, "reflection_sessions", "status = ?", ("closed",)
                ),
                "news_sections": self._count_table(conn, "news_sections"),
                "news_sources": self._count_table(conn, "news_sources"),
                "news_items": self._count_table(conn, "news_items"),
                "news_item_summaries": self._count_table(conn, "news_item_summaries"),
                "news_briefings": self._count_table(conn, "news_briefings"),
                "heartbeat_logs": self._count_table(conn, "heartbeat_logs"),
            }
            latest = {
                "last_heartbeat_at": self._max_timestamp(conn, "heartbeat_logs"),
                "last_artifact_at": self._max_timestamp(conn, "artifacts"),
                "last_news_item_at": self._max_timestamp(conn, "news_items"),
            }
        payload = {
            "payload_version": 1,
            "digest_type": "system_state",
            "generated_at": timestamp,
            "counts": counts,
            "latest": latest,
            "status": {"db_path": str(self.db_path)},
        }
        return self.create_digest("system_state", payload)

    def create_codex_usage_log(
        self,
        scope_key: str,
        request_id: str | None,
        user_id: str | None,
        model_ref: str | None,
        context: str | None,
        tokens_in: int,
        tokens_out: int,
        total_tokens: int,
        latency_ms: int,
        request_count: int,
        metadata: dict[str, Any] | None,
    ) -> dict[str, Any]:
        timestamp = utc_now()
        cleaned_scope = (scope_key or "global").strip() or "global"
        total = total_tokens if total_tokens > 0 else max(tokens_in + tokens_out, 0)
        payload_json = dumps_json(metadata)
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO codex_usage_logs (
                    scope_key,
                    request_id,
                    user_id,
                    model_ref,
                    context,
                    tokens_in,
                    tokens_out,
                    total_tokens,
                    latency_ms,
                    request_count,
                    metadata,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    cleaned_scope,
                    request_id,
                    user_id,
                    model_ref,
                    context,
                    tokens_in,
                    tokens_out,
                    total,
                    latency_ms,
                    request_count,
                    payload_json,
                    timestamp,
                ),
            )
            log_id = int(cursor.lastrowid)
        return {
            "usage_log_id": log_id,
            "scope_key": cleaned_scope,
            "created_at": timestamp,
            "total_tokens": total,
        }

    def upsert_codex_limits_settings(
        self,
        scope_key: str,
        window_hours: int,
        max_tokens: int,
        max_requests: int,
        max_latency_ms: int,
        warn_ratio: float,
        critical_ratio: float,
    ) -> dict[str, Any]:
        timestamp = utc_now()
        cleaned_scope = (scope_key or "global").strip() or "global"
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT id FROM codex_limits_settings WHERE scope_key = ?;",
                (cleaned_scope,),
            ).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE codex_limits_settings
                    SET window_hours = ?,
                        max_tokens = ?,
                        max_requests = ?,
                        max_latency_ms = ?,
                        warn_ratio = ?,
                        critical_ratio = ?,
                        updated_at = ?
                    WHERE scope_key = ?;
                    """,
                    (
                        window_hours,
                        max_tokens,
                        max_requests,
                        max_latency_ms,
                        warn_ratio,
                        critical_ratio,
                        timestamp,
                        cleaned_scope,
                    ),
                )
                settings_id = int(existing[0])
            else:
                cursor = conn.execute(
                    """
                    INSERT INTO codex_limits_settings (
                        scope_key,
                        window_hours,
                        max_tokens,
                        max_requests,
                        max_latency_ms,
                        warn_ratio,
                        critical_ratio,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        cleaned_scope,
                        window_hours,
                        max_tokens,
                        max_requests,
                        max_latency_ms,
                        warn_ratio,
                        critical_ratio,
                        timestamp,
                    ),
                )
                settings_id = int(cursor.lastrowid)
        return {
            "settings_id": settings_id,
            "scope_key": cleaned_scope,
            "window_hours": window_hours,
            "max_tokens": max_tokens,
            "max_requests": max_requests,
            "max_latency_ms": max_latency_ms,
            "warn_ratio": warn_ratio,
            "critical_ratio": critical_ratio,
            "updated_at": timestamp,
        }

    def get_codex_limits_settings(self, scope_key: str) -> dict[str, Any] | None:
        cleaned_scope = (scope_key or "global").strip() or "global"
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id,
                       scope_key,
                       window_hours,
                       max_tokens,
                       max_requests,
                       max_latency_ms,
                       warn_ratio,
                       critical_ratio,
                       updated_at
                FROM codex_limits_settings
                WHERE scope_key = ?;
                """,
                (cleaned_scope,),
            ).fetchone()
        if not row:
            return None
        return {
            "settings_id": row[0],
            "scope_key": row[1],
            "window_hours": row[2],
            "max_tokens": row[3],
            "max_requests": row[4],
            "max_latency_ms": row[5],
            "warn_ratio": row[6],
            "critical_ratio": row[7],
            "updated_at": row[8],
        }

    def list_codex_usage_logs(
        self,
        scope_key: str,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        cleaned_scope = (scope_key or "global").strip() or "global"
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id,
                       scope_key,
                       request_id,
                       user_id,
                       model_ref,
                       context,
                       tokens_in,
                       tokens_out,
                       total_tokens,
                       latency_ms,
                       request_count,
                       metadata,
                       created_at
                FROM codex_usage_logs
                WHERE scope_key = ?
                ORDER BY id DESC
                LIMIT ? OFFSET ?;
                """,
                (cleaned_scope, limit, offset),
            ).fetchall()
        items: list[dict[str, Any]] = []
        for row in rows:
            metadata = json.loads(row[11]) if row[11] else None
            items.append(
                {
                    "id": row[0],
                    "scope_key": row[1],
                    "request_id": row[2],
                    "user_id": row[3],
                    "model_ref": row[4],
                    "context": row[5],
                    "tokens_in": row[6],
                    "tokens_out": row[7],
                    "total_tokens": row[8],
                    "latency_ms": row[9],
                    "request_count": row[10],
                    "metadata": metadata,
                    "created_at": row[12],
                }
            )
        return items

    def get_codex_usage_status(self, scope_key: str) -> dict[str, Any]:
        settings = self.get_codex_limits_settings(scope_key)
        if settings is None:
            settings = {
                "scope_key": (scope_key or "global").strip() or "global",
                "window_hours": 24,
                "max_tokens": 0,
                "max_requests": 0,
                "max_latency_ms": 0,
                "warn_ratio": 0.70,
                "critical_ratio": 0.90,
            }
        window_hours = int(settings["window_hours"])
        now_dt = datetime.now(timezone.utc).replace(microsecond=0)
        window_start_dt = now_dt - timedelta(hours=window_hours)
        window_start = window_start_dt.isoformat()
        window_end = now_dt.isoformat()
        cleaned_scope = settings["scope_key"]
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT COALESCE(SUM(total_tokens), 0),
                       COALESCE(SUM(request_count), 0),
                       COALESCE(SUM(latency_ms), 0)
                FROM codex_usage_logs
                WHERE scope_key = ? AND created_at >= ?;
                """,
                (cleaned_scope, window_start),
            ).fetchone()
        total_tokens = int(row[0]) if row else 0
        total_requests = int(row[1]) if row else 0
        total_latency_ms = int(row[2]) if row else 0
        usage = {
            "total_tokens": total_tokens,
            "total_requests": total_requests,
            "total_latency_ms": total_latency_ms,
        }
        limits = {
            "max_tokens": int(settings["max_tokens"]),
            "max_requests": int(settings["max_requests"]),
            "max_latency_ms": int(settings["max_latency_ms"]),
        }
        warn_ratio = float(settings["warn_ratio"])
        critical_ratio = float(settings["critical_ratio"])
        percent_used: dict[str, float | None] = {}
        warnings: list[str] = []
        levels: list[str] = []

        def evaluate(metric: str, used: int, limit: int) -> None:
            if limit <= 0:
                percent_used[metric] = None
                return
            ratio = used / float(limit)
            percent_used[metric] = ratio
            if ratio >= critical_ratio:
                warnings.append(f"{metric}_critical")
                levels.append("critical")
            elif ratio >= warn_ratio:
                warnings.append(f"{metric}_warn")
                levels.append("warn")
            else:
                levels.append("ok")

        evaluate("tokens", total_tokens, limits["max_tokens"])
        evaluate("requests", total_requests, limits["max_requests"])
        evaluate("latency_ms", total_latency_ms, limits["max_latency_ms"])

        status_level = "ok"
        if "critical" in levels:
            status_level = "critical"
        elif "warn" in levels:
            status_level = "warn"
        elif all(value is None for value in percent_used.values()):
            status_level = "no_limits"

        return {
            "scope_key": cleaned_scope,
            "window_hours": window_hours,
            "window_start": window_start,
            "window_end": window_end,
            "usage": usage,
            "limits": limits,
            "percent_used": percent_used,
            "warn_ratio": warn_ratio,
            "critical_ratio": critical_ratio,
            "status_level": status_level,
            "warnings": warnings,
            "economy_mode_consider": status_level == "warn",
            "economy_mode_recommended": status_level == "critical",
        }

    def create_artifact(self, payload: IngestPayload) -> int:
        timestamp = utc_now()
        content_hash = payload.content_hash
        if payload.content and not content_hash:
            content_hash = compute_hash(payload.content)
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO artifacts (
                    external_id,
                    source_type,
                    source_ref,
                    content_type,
                    content_path,
                    content_hash,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    payload.external_id,
                    payload.source_type,
                    payload.source_ref,
                    payload.content_type,
                    payload.content_path,
                    content_hash,
                    timestamp,
                    timestamp,
                ),
            )
            return int(cursor.lastrowid)

    def create_summary(
        self,
        artifact_id: int,
        summary_text: str,
        summary_format: str,
        model_ref: str,
    ) -> int:
        if not summary_text.strip():
            raise SidecarError("summary_error", "Summary text is empty.")
        timestamp = utc_now()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO artifact_summaries (
                    artifact_id,
                    summary_text,
                    summary_format,
                    model_ref,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?);
                """,
                (
                    artifact_id,
                    summary_text,
                    summary_format,
                    model_ref,
                    timestamp,
                    timestamp,
                ),
            )
            return int(cursor.lastrowid)

    def create_event(
        self,
        title: str,
        body: str | None,
        start_at: str | None,
        end_at: str | None,
        status: str,
        source_type: str | None,
        source_ref: str | None,
    ) -> int:
        timestamp = utc_now()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO events (
                    title,
                    body,
                    start_at,
                    end_at,
                    status,
                    source_type,
                    source_ref,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    title,
                    body,
                    start_at,
                    end_at,
                    status,
                    source_type,
                    source_ref,
                    timestamp,
                    timestamp,
                ),
            )
            return int(cursor.lastrowid)

    def list_events(
        self,
        status: str | None,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        query = "SELECT id, title, body, start_at, end_at, status, source_type, source_ref, created_at, updated_at FROM events"
        params: list[Any] = []
        if status:
            query += " WHERE status = ?"
            params.append(status)
        query += " ORDER BY id DESC LIMIT ? OFFSET ?;"
        params.extend([limit, offset])
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [
            {
                "id": row[0],
                "title": row[1],
                "body": row[2],
                "start_at": row[3],
                "end_at": row[4],
                "status": row[5],
                "source_type": row[6],
                "source_ref": row[7],
                "created_at": row[8],
                "updated_at": row[9],
            }
            for row in rows
        ]

    def update_event_status(self, event_id: int, status: str) -> None:
        timestamp = utc_now()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE events
                SET status = ?, updated_at = ?
                WHERE id = ?;
                """,
                (status, timestamp, event_id),
            )
            if cursor.rowcount == 0:
                raise SidecarError("not_found", f"Event {event_id} not found.")

    def create_reminder(
        self,
        event_id: int,
        remind_at: str,
        status: str,
    ) -> int:
        timestamp = utc_now()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO event_reminders (
                    event_id,
                    remind_at,
                    status,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?);
                """,
                (event_id, remind_at, status, timestamp, timestamp),
            )
            return int(cursor.lastrowid)

    def list_reminders(
        self,
        status: str | None,
        due_before: str | None,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        query = (
            "SELECT id, event_id, remind_at, status, triggered_at, created_at, updated_at "
            "FROM event_reminders"
        )
        params: list[Any] = []
        conditions: list[str] = []
        if status:
            conditions.append("status = ?")
            params.append(status)
        if due_before:
            conditions.append("remind_at <= ?")
            params.append(due_before)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY id DESC LIMIT ? OFFSET ?;"
        params.extend([limit, offset])
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [
            {
                "id": row[0],
                "event_id": row[1],
                "remind_at": row[2],
                "status": row[3],
                "triggered_at": row[4],
                "created_at": row[5],
                "updated_at": row[6],
            }
            for row in rows
        ]

    def update_reminder_status(self, reminder_id: int, status: str) -> None:
        timestamp = utc_now()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE event_reminders
                SET status = ?, updated_at = ?
                WHERE id = ?;
                """,
                (status, timestamp, reminder_id),
            )
            if cursor.rowcount == 0:
                raise SidecarError(
                    "not_found", f"Reminder {reminder_id} not found."
                )

    def list_due_reminders(self, now_iso: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, event_id, remind_at, status, triggered_at, created_at, updated_at
                FROM event_reminders
                WHERE status = 'pending' AND remind_at <= ?
                ORDER BY remind_at ASC;
                """,
                (now_iso,),
            ).fetchall()
        return [
            {
                "id": row[0],
                "event_id": row[1],
                "remind_at": row[2],
                "status": row[3],
                "triggered_at": row[4],
                "created_at": row[5],
                "updated_at": row[6],
            }
            for row in rows
        ]

    def mark_reminder_triggered(self, reminder_id: int) -> None:
        timestamp = utc_now()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE event_reminders
                SET status = 'triggered', triggered_at = ?, updated_at = ?
                WHERE id = ?;
                """,
                (timestamp, timestamp, reminder_id),
            )
            if cursor.rowcount == 0:
                raise SidecarError(
                    "not_found", f"Reminder {reminder_id} not found."
                )

    def create_parse_log(
        self,
        source_type: str | None,
        source_ref: str | None,
        input_excerpt: str,
        input_hash: str | None,
        input_length: int,
        parse_status: str,
        error_message: str | None,
        event_id: int | None,
    ) -> int:
        timestamp = utc_now()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO event_parse_logs (
                    source_type,
                    source_ref,
                    input_excerpt,
                    input_hash,
                    input_length,
                    parse_status,
                    error_message,
                    event_id,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    source_type,
                    source_ref,
                    input_excerpt,
                    input_hash,
                    input_length,
                    parse_status,
                    error_message,
                    event_id,
                    timestamp,
                ),
            )
            return int(cursor.lastrowid)

    def create_english_word(self, word: str) -> int:
        cleaned = word.strip().lower()
        if not cleaned:
            raise SidecarError("invalid_payload", "Word is required.")
        timestamp = utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO english_words (
                    word,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?);
                """,
                (cleaned, timestamp, timestamp),
            )
            row = conn.execute(
                "SELECT id FROM english_words WHERE word = ?;",
                (cleaned,),
            ).fetchone()
        if not row:
            raise SidecarError("storage_error", "Failed to insert word.")
        return int(row[0])

    def list_english_words(self, limit: int, offset: int) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, word, created_at, updated_at
                FROM english_words
                ORDER BY id DESC
                LIMIT ? OFFSET ?;
                """,
                (limit, offset),
            ).fetchall()
        return [
            {
                "id": row[0],
                "word": row[1],
                "created_at": row[2],
                "updated_at": row[3],
            }
            for row in rows
        ]

    def create_english_topic(self, name: str) -> int:
        cleaned = name.strip()
        if not cleaned:
            raise SidecarError("invalid_payload", "Topic name is required.")
        timestamp = utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO english_topics (
                    name,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?);
                """,
                (cleaned, timestamp, timestamp),
            )
            row = conn.execute(
                "SELECT id FROM english_topics WHERE name = ?;",
                (cleaned,),
            ).fetchone()
        if not row:
            raise SidecarError("storage_error", "Failed to insert topic.")
        return int(row[0])

    def list_english_topics(self, limit: int, offset: int) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, name, created_at, updated_at
                FROM english_topics
                ORDER BY id DESC
                LIMIT ? OFFSET ?;
                """,
                (limit, offset),
            ).fetchall()
        return [
            {
                "id": row[0],
                "name": row[1],
                "created_at": row[2],
                "updated_at": row[3],
            }
            for row in rows
        ]

    def create_english_session(self, topic_id: int | None) -> int:
        timestamp = utc_now()
        with self._connect() as conn:
            if topic_id is not None:
                row = conn.execute(
                    "SELECT id FROM english_topics WHERE id = ?;",
                    (topic_id,),
                ).fetchone()
                if not row:
                    raise SidecarError(
                        "not_found",
                        f"English topic {topic_id} not found.",
                    )
            cursor = conn.execute(
                """
                INSERT INTO english_sessions (
                    topic_id,
                    status,
                    opened_at,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?);
                """,
                (topic_id, "open", timestamp, timestamp, timestamp),
            )
            return int(cursor.lastrowid)

    def append_english_session_turn(
        self,
        session_id: int,
        role: str,
        content: str,
    ) -> int:
        timestamp = utc_now()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT status FROM english_sessions WHERE id = ?;",
                (session_id,),
            ).fetchone()
            if not row:
                raise SidecarError("not_found", f"English session {session_id} not found.")
            if row[0] != "open":
                raise SidecarError(
                    "invalid_state",
                    f"English session {session_id} is not open.",
                )
            cursor = conn.execute(
                """
                INSERT INTO english_session_turns (
                    session_id,
                    role,
                    content,
                    created_at
                )
                VALUES (?, ?, ?, ?);
                """,
                (session_id, role, content, timestamp),
            )
            conn.execute(
                """
                UPDATE english_sessions
                SET updated_at = ?
                WHERE id = ?;
                """,
                (timestamp, session_id),
            )
            return int(cursor.lastrowid)

    def close_english_session(self, session_id: int, summary_text: str) -> None:
        timestamp = utc_now()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE english_sessions
                SET status = 'closed',
                    closed_at = ?,
                    summary_text = ?,
                    updated_at = ?
                WHERE id = ? AND status = 'open';
                """,
                (timestamp, summary_text, timestamp, session_id),
            )
            if cursor.rowcount == 0:
                row = conn.execute(
                    "SELECT id FROM english_sessions WHERE id = ?;",
                    (session_id,),
                ).fetchone()
                if not row:
                    raise SidecarError(
                        "not_found",
                        f"English session {session_id} not found.",
                    )
                raise SidecarError(
                    "invalid_state",
                    f"English session {session_id} is not open.",
                )

    def create_reflection_session(self) -> int:
        timestamp = utc_now()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO reflection_sessions (
                    status,
                    opened_at,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?);
                """,
                ("open", timestamp, timestamp, timestamp),
            )
            return int(cursor.lastrowid)

    def append_reflection_turn(
        self,
        session_id: int,
        role: str,
        content: str,
    ) -> int:
        timestamp = utc_now()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT status FROM reflection_sessions WHERE id = ?;",
                (session_id,),
            ).fetchone()
            if not row:
                raise SidecarError(
                    "not_found", f"Reflection session {session_id} not found."
                )
            if row[0] != "open":
                raise SidecarError(
                    "invalid_state",
                    f"Reflection session {session_id} is not open.",
                )
            cursor = conn.execute(
                """
                INSERT INTO reflection_turns (
                    session_id,
                    role,
                    content,
                    created_at
                )
                VALUES (?, ?, ?, ?);
                """,
                (session_id, role, content, timestamp),
            )
            conn.execute(
                """
                UPDATE reflection_sessions
                SET updated_at = ?
                WHERE id = ?;
                """,
                (timestamp, session_id),
            )
            return int(cursor.lastrowid)

    def close_reflection_session(self, session_id: int, summary_text: str) -> None:
        timestamp = utc_now()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE reflection_sessions
                SET status = 'closed',
                    closed_at = ?,
                    summary_text = ?,
                    updated_at = ?
                WHERE id = ? AND status = 'open';
                """,
                (timestamp, summary_text, timestamp, session_id),
            )
            if cursor.rowcount == 0:
                row = conn.execute(
                    "SELECT id FROM reflection_sessions WHERE id = ?;",
                    (session_id,),
                ).fetchone()
                if not row:
                    raise SidecarError(
                        "not_found",
                        f"Reflection session {session_id} not found.",
                    )
                raise SidecarError(
                    "invalid_state",
                    f"Reflection session {session_id} is not open.",
                )

    def list_reflection_sessions(
        self,
        status: str | None,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        query = (
            "SELECT id, status, opened_at, closed_at, summary_text, created_at, updated_at "
            "FROM reflection_sessions"
        )
        params: list[Any] = []
        if status:
            query += " WHERE status = ?"
            params.append(status)
        query += " ORDER BY id DESC LIMIT ? OFFSET ?;"
        params.extend([limit, offset])
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [
            {
                "id": row[0],
                "status": row[1],
                "opened_at": row[2],
                "closed_at": row[3],
                "summary_text": row[4],
                "created_at": row[5],
                "updated_at": row[6],
            }
            for row in rows
        ]

    def create_health_record(
        self,
        title: str,
        record_type: str | None,
        notes: str | None,
        occurred_at: str | None,
        source_type: str | None,
        source_ref: str | None,
    ) -> int:
        cleaned_title = title.strip()
        if not cleaned_title:
            raise SidecarError("invalid_payload", "Health record title is required.")
        cleaned_type = record_type.strip() if record_type and record_type.strip() else None
        cleaned_notes = notes.strip() if notes and notes.strip() else None
        timestamp = utc_now()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO health_records (
                    record_type,
                    title,
                    notes,
                    occurred_at,
                    source_type,
                    source_ref,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    cleaned_type,
                    cleaned_title,
                    cleaned_notes,
                    occurred_at,
                    source_type,
                    source_ref,
                    timestamp,
                    timestamp,
                ),
            )
            return int(cursor.lastrowid)

    def list_health_records(self, limit: int, offset: int) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id,
                       record_type,
                       title,
                       notes,
                       occurred_at,
                       source_type,
                       source_ref,
                       created_at,
                       updated_at
                FROM health_records
                ORDER BY id DESC
                LIMIT ? OFFSET ?;
                """,
                (limit, offset),
            ).fetchall()
        return [
            {
                "id": row[0],
                "record_type": row[1],
                "title": row[2],
                "notes": row[3],
                "occurred_at": row[4],
                "source_type": row[5],
                "source_ref": row[6],
                "created_at": row[7],
                "updated_at": row[8],
            }
            for row in rows
        ]

    def create_health_medication(
        self,
        name: str,
        dosage: str | None,
        schedule: str | None,
        started_at: str | None,
        ended_at: str | None,
        notes: str | None,
    ) -> int:
        cleaned_name = name.strip()
        if not cleaned_name:
            raise SidecarError("invalid_payload", "Medication name is required.")
        cleaned_notes = notes.strip() if notes and notes.strip() else None
        timestamp = utc_now()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO health_medications (
                    name,
                    dosage,
                    schedule,
                    started_at,
                    ended_at,
                    notes,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    cleaned_name,
                    dosage,
                    schedule,
                    started_at,
                    ended_at,
                    cleaned_notes,
                    timestamp,
                    timestamp,
                ),
            )
            return int(cursor.lastrowid)

    def list_health_medications(self, limit: int, offset: int) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id,
                       name,
                       dosage,
                       schedule,
                       started_at,
                       ended_at,
                       notes,
                       created_at,
                       updated_at
                FROM health_medications
                ORDER BY id DESC
                LIMIT ? OFFSET ?;
                """,
                (limit, offset),
            ).fetchall()
        return [
            {
                "id": row[0],
                "name": row[1],
                "dosage": row[2],
                "schedule": row[3],
                "started_at": row[4],
                "ended_at": row[5],
                "notes": row[6],
                "created_at": row[7],
                "updated_at": row[8],
            }
            for row in rows
        ]

    def create_health_treatment(
        self,
        name: str,
        description: str | None,
        started_at: str | None,
        ended_at: str | None,
        notes: str | None,
    ) -> int:
        cleaned_name = name.strip()
        if not cleaned_name:
            raise SidecarError("invalid_payload", "Treatment name is required.")
        cleaned_notes = notes.strip() if notes and notes.strip() else None
        timestamp = utc_now()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO health_treatments (
                    name,
                    description,
                    started_at,
                    ended_at,
                    notes,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    cleaned_name,
                    description,
                    started_at,
                    ended_at,
                    cleaned_notes,
                    timestamp,
                    timestamp,
                ),
            )
            return int(cursor.lastrowid)

    def list_health_treatments(self, limit: int, offset: int) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id,
                       name,
                       description,
                       started_at,
                       ended_at,
                       notes,
                       created_at,
                       updated_at
                FROM health_treatments
                ORDER BY id DESC
                LIMIT ? OFFSET ?;
                """,
                (limit, offset),
            ).fetchall()
        return [
            {
                "id": row[0],
                "name": row[1],
                "description": row[2],
                "started_at": row[3],
                "ended_at": row[4],
                "notes": row[5],
                "created_at": row[6],
                "updated_at": row[7],
            }
            for row in rows
        ]

    def create_health_observation(
        self,
        observation_type: str,
        value: str | None,
        unit: str | None,
        observed_at: str | None,
        notes: str | None,
    ) -> int:
        cleaned_type = observation_type.strip()
        if not cleaned_type:
            raise SidecarError("invalid_payload", "Observation type is required.")
        cleaned_notes = notes.strip() if notes and notes.strip() else None
        timestamp = utc_now()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO health_observations (
                    observation_type,
                    value,
                    unit,
                    observed_at,
                    notes,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    cleaned_type,
                    value,
                    unit,
                    observed_at,
                    cleaned_notes,
                    timestamp,
                    timestamp,
                ),
            )
            return int(cursor.lastrowid)

    def list_health_observations(self, limit: int, offset: int) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id,
                       observation_type,
                       value,
                       unit,
                       observed_at,
                       notes,
                       created_at,
                       updated_at
                FROM health_observations
                ORDER BY id DESC
                LIMIT ? OFFSET ?;
                """,
                (limit, offset),
            ).fetchall()
        return [
            {
                "id": row[0],
                "observation_type": row[1],
                "value": row[2],
                "unit": row[3],
                "observed_at": row[4],
                "notes": row[5],
                "created_at": row[6],
                "updated_at": row[7],
            }
            for row in rows
        ]

    def create_health_lab_report(
        self,
        artifact_id: int,
        title: str | None,
        report_date: str | None,
        notes: str | None,
    ) -> int:
        cleaned_title = title.strip() if title and title.strip() else None
        cleaned_notes = notes.strip() if notes and notes.strip() else None
        timestamp = utc_now()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id FROM artifacts WHERE id = ?;",
                (artifact_id,),
            ).fetchone()
            if not row:
                raise SidecarError(
                    "not_found", f"Artifact {artifact_id} not found."
                )
            cursor = conn.execute(
                """
                INSERT INTO health_lab_reports (
                    artifact_id,
                    title,
                    report_date,
                    notes,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?);
                """,
                (
                    artifact_id,
                    cleaned_title,
                    report_date,
                    cleaned_notes,
                    timestamp,
                    timestamp,
                ),
            )
            return int(cursor.lastrowid)

    def list_health_lab_reports(
        self,
        artifact_id: int | None,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        query = (
            "SELECT id, artifact_id, title, report_date, notes, created_at, updated_at "
            "FROM health_lab_reports"
        )
        params: list[Any] = []
        if artifact_id is not None:
            query += " WHERE artifact_id = ?"
            params.append(artifact_id)
        query += " ORDER BY id DESC LIMIT ? OFFSET ?;"
        params.extend([limit, offset])
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [
            {
                "id": row[0],
                "artifact_id": row[1],
                "title": row[2],
                "report_date": row[3],
                "notes": row[4],
                "created_at": row[5],
                "updated_at": row[6],
            }
            for row in rows
        ]

    def create_news_section(
        self,
        name: str,
        description: str | None,
        status: str,
    ) -> int:
        cleaned = name.strip()
        if not cleaned:
            raise SidecarError("invalid_payload", "Section name is required.")
        timestamp = utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO news_sections (
                    name,
                    description,
                    status,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?);
                """,
                (cleaned, description, status, timestamp, timestamp),
            )
            row = conn.execute(
                "SELECT id FROM news_sections WHERE name = ?;",
                (cleaned,),
            ).fetchone()
        if not row:
            raise SidecarError("storage_error", "Failed to insert news section.")
        return int(row[0])

    def list_news_sections(
        self,
        status: str | None,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        query = (
            "SELECT id, name, description, status, created_at, updated_at "
            "FROM news_sections"
        )
        params: list[Any] = []
        if status:
            query += " WHERE status = ?"
            params.append(status)
        query += " ORDER BY id DESC LIMIT ? OFFSET ?;"
        params.extend([limit, offset])
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [
            {
                "id": row[0],
                "name": row[1],
                "description": row[2],
                "status": row[3],
                "created_at": row[4],
                "updated_at": row[5],
            }
            for row in rows
        ]

    def update_news_section(
        self,
        section_id: int,
        name: str | None,
        description: str | None,
        status: str | None,
    ) -> None:
        updates: list[str] = []
        params: list[Any] = []
        if name is not None:
            cleaned = name.strip()
            if not cleaned:
                raise SidecarError("invalid_payload", "Section name is required.")
            updates.append("name = ?")
            params.append(cleaned)
        if description is not None:
            updates.append("description = ?")
            params.append(description)
        if status is not None:
            updates.append("status = ?")
            params.append(status)
        if not updates:
            raise SidecarError("invalid_payload", "No updates provided.")
        timestamp = utc_now()
        updates.append("updated_at = ?")
        params.append(timestamp)
        params.append(section_id)
        with self._connect() as conn:
            cursor = conn.execute(
                f"""
                UPDATE news_sections
                SET {", ".join(updates)}
                WHERE id = ?;
                """,
                params,
            )
            if cursor.rowcount == 0:
                raise SidecarError(
                    "not_found", f"News section {section_id} not found."
                )

    def create_news_source(
        self,
        section_id: int,
        name: str,
        source_type: str,
        source_ref: str | None,
        status: str,
    ) -> int:
        cleaned = name.strip()
        if not cleaned:
            raise SidecarError("invalid_payload", "Source name is required.")
        timestamp = utc_now()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id FROM news_sections WHERE id = ?;",
                (section_id,),
            ).fetchone()
            if not row:
                raise SidecarError(
                    "not_found", f"News section {section_id} not found."
                )
            conn.execute(
                """
                INSERT OR IGNORE INTO news_sources (
                    section_id,
                    name,
                    source_type,
                    source_ref,
                    status,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (section_id, cleaned, source_type, source_ref, status, timestamp, timestamp),
            )
            row = conn.execute(
                """
                SELECT id FROM news_sources
                WHERE section_id = ? AND name = ?;
                """,
                (section_id, cleaned),
            ).fetchone()
        if not row:
            raise SidecarError("storage_error", "Failed to insert news source.")
        return int(row[0])

    def list_news_sources(
        self,
        section_id: int | None,
        status: str | None,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        query = (
            "SELECT id, section_id, name, source_type, source_ref, status, created_at, updated_at "
            "FROM news_sources"
        )
        params: list[Any] = []
        conditions: list[str] = []
        if section_id is not None:
            conditions.append("section_id = ?")
            params.append(section_id)
        if status:
            conditions.append("status = ?")
            params.append(status)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY id DESC LIMIT ? OFFSET ?;"
        params.extend([limit, offset])
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [
            {
                "id": row[0],
                "section_id": row[1],
                "name": row[2],
                "source_type": row[3],
                "source_ref": row[4],
                "status": row[5],
                "created_at": row[6],
                "updated_at": row[7],
            }
            for row in rows
        ]

    def update_news_source(
        self,
        source_id: int,
        section_id: int | None,
        name: str | None,
        source_type: str | None,
        source_ref: str | None,
        status: str | None,
    ) -> None:
        updates: list[str] = []
        params: list[Any] = []
        if section_id is not None:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT id FROM news_sections WHERE id = ?;",
                    (section_id,),
                ).fetchone()
            if not row:
                raise SidecarError(
                    "not_found", f"News section {section_id} not found."
                )
            updates.append("section_id = ?")
            params.append(section_id)
        if name is not None:
            cleaned = name.strip()
            if not cleaned:
                raise SidecarError("invalid_payload", "Source name is required.")
            updates.append("name = ?")
            params.append(cleaned)
        if source_type is not None:
            updates.append("source_type = ?")
            params.append(source_type)
        if source_ref is not None:
            updates.append("source_ref = ?")
            params.append(source_ref)
        if status is not None:
            updates.append("status = ?")
            params.append(status)
        if not updates:
            raise SidecarError("invalid_payload", "No updates provided.")
        timestamp = utc_now()
        updates.append("updated_at = ?")
        params.append(timestamp)
        params.append(source_id)
        with self._connect() as conn:
            cursor = conn.execute(
                f"""
                UPDATE news_sources
                SET {", ".join(updates)}
                WHERE id = ?;
                """,
                params,
            )
            if cursor.rowcount == 0:
                raise SidecarError(
                    "not_found", f"News source {source_id} not found."
                )

    def ingest_news_item(
        self,
        section_id: int,
        source_id: int,
        external_id: str | None,
        title: str | None,
        url: str | None,
        published_at: str | None,
        content_text: str | None,
        raw_payload: dict[str, Any] | None,
    ) -> dict[str, Any]:
        timestamp = utc_now()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT section_id FROM news_sources WHERE id = ?;",
                (source_id,),
            ).fetchone()
            if not row:
                raise SidecarError("not_found", f"News source {source_id} not found.")
            if int(row[0]) != section_id:
                raise SidecarError(
                    "invalid_payload",
                    "Source does not belong to the provided section.",
                )
            row = conn.execute(
                "SELECT id FROM news_sections WHERE id = ?;",
                (section_id,),
            ).fetchone()
            if not row:
                raise SidecarError(
                    "not_found", f"News section {section_id} not found."
                )
            content_hash = normalize_news_hash_payload(
                title=title,
                url=url,
                published_at=published_at,
                content_text=content_text,
                external_id=external_id,
                raw_payload=raw_payload,
            )
            raw_payload_json = (
                json.dumps(raw_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
                if raw_payload is not None
                else None
            )
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO news_items (
                    section_id,
                    source_id,
                    external_id,
                    title,
                    url,
                    published_at,
                    content_text,
                    content_hash,
                    raw_payload,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    section_id,
                    source_id,
                    external_id,
                    title,
                    url,
                    published_at,
                    content_text,
                    content_hash,
                    raw_payload_json,
                    timestamp,
                    timestamp,
                ),
            )
            if cursor.rowcount == 0:
                row = conn.execute(
                    """
                    SELECT id FROM news_items
                    WHERE source_id = ? AND content_hash = ?;
                    """,
                    (source_id, content_hash),
                ).fetchone()
                if not row:
                    raise SidecarError("storage_error", "Failed to insert news item.")
                return {"news_item_id": int(row[0]), "deduped": True}
            return {"news_item_id": int(cursor.lastrowid), "deduped": False}

    def get_news_item(self, news_item_id: int) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT ni.id,
                       ni.section_id,
                       ni.source_id,
                       ni.title,
                       ni.url,
                       ni.published_at,
                       ni.content_text,
                       ni.created_at,
                       ni.updated_at,
                       ns.name,
                       ns.source_type,
                       ns.source_ref
                FROM news_items ni
                JOIN news_sources ns ON ns.id = ni.source_id
                WHERE ni.id = ?;
                """,
                (news_item_id,),
            ).fetchone()
        if not row:
            raise SidecarError("not_found", f"News item {news_item_id} not found.")
        return {
            "id": row[0],
            "section_id": row[1],
            "source_id": row[2],
            "title": row[3],
            "url": row[4],
            "published_at": row[5],
            "content_text": row[6],
            "created_at": row[7],
            "updated_at": row[8],
            "source_name": row[9],
            "source_type": row[10],
            "source_ref": row[11],
        }

    def list_news_items_for_briefing(
        self,
        section_id: int | None,
        source_id: int | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        query = (
            "SELECT ni.id, ni.section_id, ni.source_id, ni.title, ni.url, "
            "ni.published_at, ni.content_text, ni.created_at, ni.updated_at, "
            "ns.name, ns.source_type, ns.source_ref "
            "FROM news_items ni "
            "JOIN news_sources ns ON ns.id = ni.source_id"
        )
        params: list[Any] = []
        conditions: list[str] = []
        if section_id is not None:
            conditions.append("ni.section_id = ?")
            params.append(section_id)
        if source_id is not None:
            conditions.append("ni.source_id = ?")
            params.append(source_id)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += (
            " ORDER BY (ni.published_at IS NULL) ASC, "
            "ni.published_at DESC, ni.created_at DESC, ni.id DESC "
            "LIMIT ?;"
        )
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [
            {
                "id": row[0],
                "section_id": row[1],
                "source_id": row[2],
                "title": row[3],
                "url": row[4],
                "published_at": row[5],
                "content_text": row[6],
                "created_at": row[7],
                "updated_at": row[8],
                "source_name": row[9],
                "source_type": row[10],
                "source_ref": row[11],
            }
            for row in rows
        ]

    def get_news_item_summary(self, news_item_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, summary_text, summary_format, model_ref, created_at, updated_at
                FROM news_item_summaries
                WHERE news_item_id = ?;
                """,
                (news_item_id,),
            ).fetchone()
        if not row:
            return None
        return {
            "id": row[0],
            "summary_text": row[1],
            "summary_format": row[2],
            "model_ref": row[3],
            "created_at": row[4],
            "updated_at": row[5],
        }

    def upsert_news_item_summary(
        self,
        news_item_id: int,
        summary_text: str,
        summary_format: str,
        model_ref: str,
    ) -> int:
        if not summary_text.strip():
            raise SidecarError("summary_error", "Summary text is empty.")
        timestamp = utc_now()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id FROM news_items WHERE id = ?;",
                (news_item_id,),
            ).fetchone()
            if not row:
                raise SidecarError(
                    "not_found", f"News item {news_item_id} not found."
                )
            existing = conn.execute(
                "SELECT id FROM news_item_summaries WHERE news_item_id = ?;",
                (news_item_id,),
            ).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE news_item_summaries
                    SET summary_text = ?,
                        summary_format = ?,
                        model_ref = ?,
                        updated_at = ?
                    WHERE news_item_id = ?;
                    """,
                    (summary_text, summary_format, model_ref, timestamp, news_item_id),
                )
                return int(existing[0])
            cursor = conn.execute(
                """
                INSERT INTO news_item_summaries (
                    news_item_id,
                    summary_text,
                    summary_format,
                    model_ref,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?);
                """,
                (news_item_id, summary_text, summary_format, model_ref, timestamp, timestamp),
            )
            return int(cursor.lastrowid)

    def create_news_briefing(self, briefing_mode: str) -> int:
        timestamp = utc_now()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO news_briefings (
                    briefing_mode,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?);
                """,
                (briefing_mode, timestamp, timestamp),
            )
            return int(cursor.lastrowid)

    def add_news_briefing_item(
        self,
        briefing_id: int,
        news_item_id: int,
        source_id: int,
        title: str | None,
        url: str | None,
        published_at: str | None,
        summary_text: str,
    ) -> int:
        if not summary_text.strip():
            raise SidecarError("summary_error", "Summary text is empty.")
        timestamp = utc_now()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO news_briefing_items (
                    briefing_id,
                    news_item_id,
                    source_id,
                    title,
                    url,
                    published_at,
                    summary_text,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    briefing_id,
                    news_item_id,
                    source_id,
                    title,
                    url,
                    published_at,
                    summary_text,
                    timestamp,
                ),
            )
            return int(cursor.lastrowid)

    def get_briefing(self, briefing_id: int) -> dict[str, Any]:
        with self._connect() as conn:
            briefing = conn.execute(
                """
                SELECT id, briefing_mode, created_at, updated_at
                FROM news_briefings
                WHERE id = ?;
                """,
                (briefing_id,),
            ).fetchone()
            if not briefing:
                raise SidecarError("not_found", f"Briefing {briefing_id} not found.")
            items = conn.execute(
                """
                SELECT nbi.id,
                       nbi.news_item_id,
                       nbi.source_id,
                       nbi.title,
                       nbi.url,
                       nbi.published_at,
                       nbi.summary_text,
                       nbi.created_at,
                       ns.name,
                       ns.source_type,
                       ns.source_ref
                FROM news_briefing_items nbi
                JOIN news_sources ns ON ns.id = nbi.source_id
                WHERE nbi.briefing_id = ?
                ORDER BY nbi.id ASC;
                """,
                (briefing_id,),
            ).fetchall()
        return {
            "id": briefing[0],
            "briefing_mode": briefing[1],
            "created_at": briefing[2],
            "updated_at": briefing[3],
            "items": [
                {
                    "id": row[0],
                    "news_item_id": row[1],
                    "source_id": row[2],
                    "title": row[3],
                    "url": row[4],
                    "published_at": row[5],
                    "summary_text": row[6],
                    "created_at": row[7],
                    "source_name": row[8],
                    "source_type": row[9],
                    "source_ref": row[10],
                }
                for row in items
            ],
        }

    def get_latest_briefing(self) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id FROM news_briefings
                ORDER BY id DESC
                LIMIT 1;
                """,
            ).fetchone()
        if not row:
            raise SidecarError("not_found", "No briefings found.")
        return self.get_briefing(int(row[0]))

    def list_briefings(self, limit: int, offset: int) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, briefing_mode, created_at, updated_at
                FROM news_briefings
                ORDER BY id DESC
                LIMIT ? OFFSET ?;
                """,
                (limit, offset),
            ).fetchall()
        return [
            {
                "id": row[0],
                "briefing_mode": row[1],
                "created_at": row[2],
                "updated_at": row[3],
            }
            for row in rows
        ]

    def create_note(
        self,
        title: str | None,
        body: str,
        source_type: str | None,
        source_ref: str | None,
    ) -> int:
        if not body.strip():
            raise SidecarError("invalid_payload", "Note body is required.")
        timestamp = utc_now()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO notes (
                    title,
                    body,
                    source_type,
                    source_ref,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?);
                """,
                (title, body, source_type, source_ref, timestamp, timestamp),
            )
            return int(cursor.lastrowid)
