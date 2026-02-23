"""SQLite storage helpers for sidecar ingestion."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
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


@dataclass(slots=True)
class SQLiteStore:
    """SQLite-backed storage for artifacts and summaries."""

    db_path: Path

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

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
