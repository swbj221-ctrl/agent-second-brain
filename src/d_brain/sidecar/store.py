"""SQLite storage helpers for sidecar ingestion."""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

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
