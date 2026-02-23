#!/usr/bin/env python3
"""Smoke test for Stage 6 news briefing (second pass)."""

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
        before_briefings = conn.execute(
            "SELECT COUNT(*) FROM news_briefings;"
        ).fetchone()[0]
        before_items = conn.execute(
            "SELECT COUNT(*) FROM news_briefing_items;"
        ).fetchone()[0]
        before_notes = conn.execute("SELECT COUNT(*) FROM notes;").fetchone()[0]

    section_request = {
        "request_id": "news-briefing-smoke-001",
        "user_id": "smoke-user",
        "action": "news_section_create",
        "payload": {"name": "Briefing Smoke Section", "description": "Smoke test."},
    }
    section_response = handle_request(section_request, settings=settings)
    print(json.dumps(section_response, indent=2))
    section_id = section_response.get("data", {}).get("section_id")

    source_requests = [
        {
            "request_id": "news-briefing-smoke-002",
            "user_id": "smoke-user",
            "action": "news_source_create",
            "payload": {
                "section_id": section_id,
                "name": "Briefing Smoke Source A",
                "source_type": "manual",
                "source_ref": "local-a",
            },
        },
        {
            "request_id": "news-briefing-smoke-003",
            "user_id": "smoke-user",
            "action": "news_source_create",
            "payload": {
                "section_id": section_id,
                "name": "Briefing Smoke Source B",
                "source_type": "manual",
                "source_ref": "local-b",
            },
        },
    ]
    source_ids: list[int] = []
    for request in source_requests:
        response = handle_request(request, settings=settings)
        print(json.dumps(response, indent=2))
        source_ids.append(response.get("data", {}).get("source_id"))

    items = [
        {
            "external_id": "briefing-item-001",
            "title": "Smoke Item One",
            "url": "https://example.com/briefing-001",
            "published_at": "2026-02-23T10:00:00Z",
            "content_text": "Briefing smoke content one.",
            "raw_payload": {"source": "manual", "index": 1},
            "source_id": source_ids[0],
        },
        {
            "external_id": "briefing-item-002",
            "title": "Smoke Item Two",
            "url": "https://example.com/briefing-002",
            "published_at": "2026-02-23T11:00:00Z",
            "content_text": "Briefing smoke content two.",
            "raw_payload": {"source": "manual", "index": 2},
            "source_id": source_ids[0],
        },
        {
            "external_id": "briefing-item-003",
            "title": "Smoke Item Three",
            "url": "https://example.com/briefing-003",
            "published_at": "2026-02-23T12:00:00Z",
            "content_text": "Briefing smoke content three.",
            "raw_payload": {"source": "manual", "index": 3},
            "source_id": source_ids[0],
        },
        {
            "external_id": "briefing-item-004",
            "title": "Smoke Item Four",
            "url": "https://example.com/briefing-004",
            "published_at": "2026-02-23T13:00:00Z",
            "content_text": "Briefing smoke content four.",
            "raw_payload": {"source": "manual", "index": 4},
            "source_id": source_ids[0],
        },
        {
            "external_id": "briefing-item-005",
            "title": "Smoke Item Five",
            "url": "https://example.com/briefing-005",
            "published_at": "2026-02-23T14:00:00Z",
            "content_text": "Briefing smoke content five.",
            "raw_payload": {"source": "manual", "index": 5},
            "source_id": source_ids[0],
        },
        {
            "external_id": "briefing-item-006",
            "title": "Smoke Item One",
            "url": "https://example.com/briefing-001",
            "published_at": "2026-02-23T10:00:00Z",
            "content_text": "Briefing smoke content one.",
            "raw_payload": {"source": "manual", "index": 6},
            "source_id": source_ids[1],
        },
    ]

    news_item_ids: list[int] = []
    for idx, item in enumerate(items, start=1):
        request = {
            "request_id": f"news-briefing-smoke-1{idx:02d}",
            "user_id": "smoke-user",
            "action": "news_item_ingest",
            "payload": {
                "section_id": section_id,
                "source_id": item["source_id"],
                "external_id": item["external_id"],
                "title": item["title"],
                "url": item["url"],
                "published_at": item["published_at"],
                "content_text": item["content_text"],
                "raw_payload": item["raw_payload"],
            },
        }
        response = handle_request(request, settings=settings)
        print(json.dumps(response, indent=2))
        news_item_ids.append(response.get("data", {}).get("news_item_id"))

    for idx, news_item_id in enumerate(news_item_ids, start=1):
        summarize_request = {
            "request_id": f"news-briefing-smoke-2{idx:02d}",
            "user_id": "smoke-user",
            "action": "news_item_summarize",
            "payload": {"news_item_id": news_item_id},
        }
        summarize_response = handle_request(summarize_request, settings=settings)
        print(json.dumps(summarize_response, indent=2))

    briefing_request = {
        "request_id": "news-briefing-smoke-301",
        "user_id": "smoke-user",
        "action": "news_briefing_generate",
        "payload": {"section_id": section_id, "limit": 50},
    }
    briefing_response = handle_request(briefing_request, settings=settings)
    print(json.dumps(briefing_response, indent=2))
    briefing_id = briefing_response.get("data", {}).get("briefing_id")

    save_request = {
        "request_id": "news-briefing-smoke-401",
        "user_id": "smoke-user",
        "action": "news_item_save_to_db",
        "payload": {"news_item_id": news_item_ids[0]},
    }
    save_response = handle_request(save_request, settings=settings)
    print(json.dumps(save_response, indent=2))

    with sqlite3.connect(settings.db_path) as conn:
        after_briefings = conn.execute(
            "SELECT COUNT(*) FROM news_briefings;"
        ).fetchone()[0]
        after_items = conn.execute(
            "SELECT COUNT(*) FROM news_briefing_items;"
        ).fetchone()[0]
        after_notes = conn.execute("SELECT COUNT(*) FROM notes;").fetchone()[0]
        briefing_item_count = conn.execute(
            "SELECT COUNT(*) FROM news_briefing_items WHERE briefing_id = ?;",
            (briefing_id,),
        ).fetchone()[0]
        source_refs = conn.execute(
            """
            SELECT COUNT(*) FROM news_briefing_items
            WHERE briefing_id = ?
              AND source_id IS NOT NULL
              AND (url IS NOT NULL AND url != '');
            """,
            (briefing_id,),
        ).fetchone()[0]

    print(f"briefings_delta={after_briefings - before_briefings}")
    print(f"briefing_items_delta={after_items - before_items}")
    print(f"notes_delta={after_notes - before_notes}")
    print(f"briefing_item_count={briefing_item_count}")
    print(f"briefing_items_with_source_and_url={source_refs}")

    if briefing_item_count != 5:
        raise SystemExit("briefing_items_count_failed")
    if source_refs != 5:
        raise SystemExit("briefing_source_refs_failed")
    if after_notes - before_notes < 1:
        raise SystemExit("briefing_notes_save_failed")

    print("stage6_news_briefing_smoke_ok")


if __name__ == "__main__":
    main()
