"""News briefing helpers for Stage 6 second pass."""

from __future__ import annotations

import logging
from typing import Any

from .errors import SidecarError
from .summarizer import HeuristicSummarizer, normalize_text
from .store import SQLiteStore


def build_briefing_key(item: dict[str, Any]) -> str:
    title = normalize_text(item.get("title") or "").lower()
    url = normalize_text(item.get("url") or "").lower()
    published_at = normalize_text(item.get("published_at") or "")
    content_text = normalize_text(item.get("content_text") or "").lower()
    return "|".join([title, url, published_at, content_text])


def select_briefing_items(
    candidates: list[dict[str, Any]],
    target_count: int = 5,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in candidates:
        key = build_briefing_key(item)
        if key in seen:
            continue
        seen.add(key)
        selected.append(item)
        if len(selected) >= target_count:
            break
    return selected


def summarize_news_item(
    store: SQLiteStore,
    news_item_id: int,
    summary_format: str = "plain",
    summarizer: HeuristicSummarizer | None = None,
) -> dict[str, Any]:
    summarizer = summarizer or HeuristicSummarizer()
    item = store.get_news_item(news_item_id)
    content_text = (item.get("content_text") or "").strip()
    title = (item.get("title") or "").strip()
    source_text = content_text or title
    if not source_text:
        raise SidecarError("invalid_payload", "News item has no text to summarize.")
    result = summarizer.summarize(source_text, summary_format=summary_format)
    summary_id = store.upsert_news_item_summary(
        news_item_id,
        result.summary_text,
        result.summary_format,
        result.model_ref,
    )
    try:
        store.create_heartbeat_log(
            event_type="utility_usage",
            event_source="utility:summarizer",
            event_details={
                "utility": "summarizer",
                "model_ref": result.model_ref,
                "summary_format": result.summary_format,
                "context": "news",
            },
        )
    except Exception:
        logging.getLogger(__name__).exception("Failed to record utility usage event")
    return {
        "summary_id": summary_id,
        "news_item_id": news_item_id,
        "summary_text": result.summary_text,
        "summary_format": result.summary_format,
        "model_ref": result.model_ref,
    }


def generate_manual_briefing(
    store: SQLiteStore,
    section_id: int | None = None,
    source_id: int | None = None,
    limit: int = 50,
    target_count: int = 5,
    briefing_mode: str = "manual",
) -> dict[str, Any]:
    candidates = store.list_news_items_for_briefing(section_id, source_id, limit)
    selected = select_briefing_items(candidates, target_count=target_count)
    if len(selected) < target_count:
        raise SidecarError(
            "insufficient_items",
            f"Need {target_count} unique items to build a briefing.",
        )
    summarizer = HeuristicSummarizer()
    briefing_id = store.create_news_briefing(briefing_mode)
    items: list[dict[str, Any]] = []
    for item in selected:
        summary = store.get_news_item_summary(item["id"])
        if summary is None:
            summary = summarize_news_item(
                store,
                item["id"],
                summary_format="plain",
                summarizer=summarizer,
            )
        item_id = store.add_news_briefing_item(
            briefing_id=briefing_id,
            news_item_id=item["id"],
            source_id=item["source_id"],
            title=item.get("title"),
            url=item.get("url"),
            published_at=item.get("published_at"),
            summary_text=summary["summary_text"],
        )
        items.append(
            {
                "briefing_item_id": item_id,
                "news_item_id": item["id"],
                "source_id": item["source_id"],
                "source_name": item.get("source_name"),
                "source_type": item.get("source_type"),
                "source_ref": item.get("source_ref"),
                "title": item.get("title"),
                "url": item.get("url"),
                "published_at": item.get("published_at"),
                "summary_text": summary["summary_text"],
            }
        )
    return {"briefing_id": briefing_id, "items": items}
