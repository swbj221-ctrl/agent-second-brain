"""SQLite storage helpers for sidecar ingestion."""

from __future__ import annotations

import hashlib
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
