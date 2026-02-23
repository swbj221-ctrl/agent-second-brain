#!/usr/bin/env python3
"""Smoke test for Stage 6 news MVP (first pass)."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = REPO_ROOT / "src"
if SRC_PATH.exists() and str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from d_brain.config import get_settings
from d_brain.sidecar.dispatcher import handle_request


def main() -> None:
    settings = get_settings()
    with sqlite3.connect(settings.db_path) as conn:
        before_sections = conn.execute(
            "SELECT COUNT(*) FROM news_sections;"
        ).fetchone()[0]
        before_sources = conn.execute(
            "SELECT COUNT(*) FROM news_sources;"
        ).fetchone()[0]
        before_items = conn.execute(
            "SELECT COUNT(*) FROM news_items;"
        ).fetchone()[0]

    section_request = {
        "request_id": "news-smoke-001",
        "user_id": "smoke-user",
        "action": "news_section_create",
        "payload": {
            "name": "Smoke Section",
            "description": "Stage 6 smoke test section.",
        },
    }
    section_response = handle_request(section_request, settings=settings)
    print(json.dumps(section_response, indent=2))
    section_id = section_response.get("data", {}).get("section_id")

    source_request = {
        "request_id": "news-smoke-002",
        "user_id": "smoke-user",
        "action": "news_source_create",
        "payload": {
            "section_id": section_id,
            "name": "Smoke Source",
            "source_type": "manual",
            "source_ref": "local",
        },
    }
    source_response = handle_request(source_request, settings=settings)
    print(json.dumps(source_response, indent=2))
    source_id = source_response.get("data", {}).get("source_id")

    item_payload = {
        "section_id": section_id,
        "source_id": source_id,
        "external_id": "smoke-item-001",
        "title": "Smoke Item One",
        "url": "https://example.com/smoke-item-001",
        "published_at": "2026-02-23T00:00:00Z",
        "content_text": "Stage 6 smoke test news item content.",
        "raw_payload": {"source": "manual", "index": 1},
    }

    item_request = {
        "request_id": "news-smoke-003",
        "user_id": "smoke-user",
        "action": "news_item_ingest",
        "payload": item_payload,
    }
    item_response = handle_request(item_request, settings=settings)
    print(json.dumps(item_response, indent=2))

    duplicate_request = {
        "request_id": "news-smoke-004",
        "user_id": "smoke-user",
        "action": "news_item_ingest",
        "payload": item_payload,
    }
    duplicate_response = handle_request(duplicate_request, settings=settings)
    print(json.dumps(duplicate_response, indent=2))

    second_item_request = {
        "request_id": "news-smoke-005",
        "user_id": "smoke-user",
        "action": "news_item_ingest",
        "payload": {
            "section_id": section_id,
            "source_id": source_id,
            "external_id": "smoke-item-002",
            "title": "Smoke Item Two",
            "url": "https://example.com/smoke-item-002",
            "published_at": "2026-02-23T01:00:00Z",
            "content_text": "Stage 6 smoke test news item content two.",
            "raw_payload": {"source": "manual", "index": 2},
        },
    }
    second_item_response = handle_request(second_item_request, settings=settings)
    print(json.dumps(second_item_response, indent=2))

    with sqlite3.connect(settings.db_path) as conn:
        after_sections = conn.execute(
            "SELECT COUNT(*) FROM news_sections;"
        ).fetchone()[0]
        after_sources = conn.execute(
            "SELECT COUNT(*) FROM news_sources;"
        ).fetchone()[0]
        after_items = conn.execute(
            "SELECT COUNT(*) FROM news_items;"
        ).fetchone()[0]

    print(f"sections_delta={after_sections - before_sections}")
    print(f"sources_delta={after_sources - before_sources}")
    print(f"items_delta={after_items - before_items}")

    if after_items - before_items != 2:
        raise SystemExit("news_items_dedupe_failed")

    print("stage6_news_smoke_ok")


if __name__ == "__main__":
    main()
