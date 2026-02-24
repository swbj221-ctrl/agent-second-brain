"""Web search and summarize helpers (Telegram UX)."""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import shutil
from typing import Any

from .command_runner import CommandResult, run_command

logger = logging.getLogger(__name__)


@dataclass
class SearchItem:
    title: str
    url: str
    snippet: str | None = None


@dataclass
class SearchResult:
    ok: bool
    items: list[SearchItem]
    error_message: str | None = None
    raw_error: str | None = None


@dataclass
class TextResult:
    ok: bool
    text: str
    error_message: str | None = None
    raw_error: str | None = None
    truncated: bool = False


def _command_available(name: str) -> bool:
    return shutil.which(name) is not None


def _parse_tavily_results(payload: dict[str, Any]) -> list[SearchItem]:
    raw_items = payload.get("results")
    if not isinstance(raw_items, list):
        return []
    items: list[SearchItem] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        url = str(item.get("url") or "").strip()
        snippet = str(item.get("content") or item.get("snippet") or "").strip()
        if not title and not url:
            continue
        items.append(SearchItem(title=title, url=url, snippet=snippet or None))
    return items


def _run_tavily_search(query: str, max_results: int) -> CommandResult:
    payload = {
        "query": query,
        "search_depth": "basic",
        "max_results": max_results,
    }
    return run_command(
        ["mcp-cli", "call", "tavily", "tavily-search", json.dumps(payload)],
        timeout_sec=45,
        max_output_chars=12000,
    )


def search_web(query: str, max_results: int = 5) -> SearchResult:
    if not _command_available("mcp-cli"):
        return SearchResult(
            ok=False,
            items=[],
            error_message="Web search unavailable. MCP CLI is not installed.",
        )

    result = _run_tavily_search(query, max_results=max_results)
    if not result.ok:
        logger.warning("Tavily search failed: %s", result.stderr or result.error_message)
        return SearchResult(
            ok=False,
            items=[],
            error_message="Web search failed. Check MCP setup.",
            raw_error=(result.stderr or result.error_message),
        )

    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        logger.warning("Failed to parse Tavily output")
        return SearchResult(
            ok=False,
            items=[],
            error_message="Web search failed. Invalid response.",
            raw_error=result.stdout,
        )

    items = _parse_tavily_results(payload)
    if not items:
        return SearchResult(
            ok=False,
            items=[],
            error_message="No results found.",
        )
    return SearchResult(ok=True, items=items, error_message=None)


def _summarize_command_args(url: str) -> list[str]:
    if _command_available("summarize"):
        return ["summarize", url, "--plain"]
    return ["npx", "-y", "@steipete/summarize", url, "--plain"]


def summarize_url(url: str, max_chars: int = 1500) -> TextResult:
    result = run_command(_summarize_command_args(url), timeout_sec=60, max_output_chars=16000)
    if not result.ok:
        logger.warning("Summarize failed: %s", result.stderr or result.error_message)
        return TextResult(
            ok=False,
            text="",
            error_message="Summary failed. Check summarize config.",
            raw_error=(result.stderr or result.error_message),
        )
    text = (result.stdout or "").strip()
    if not text:
        return TextResult(ok=False, text="", error_message="Summary empty.")
    if len(text) > max_chars:
        return TextResult(
            ok=True,
            text=text[: max_chars - 3].rstrip() + "...",
            truncated=True,
        )
    return TextResult(ok=True, text=text)


def _youtube_transcript_args(url: str) -> list[str]:
    if _command_available("summarize"):
        return ["summarize", url, "--youtube", "auto", "--extract", "--plain"]
    return ["npx", "-y", "@steipete/summarize", url, "--youtube", "auto", "--extract", "--plain"]


def youtube_transcript(url: str, max_chars: int = 1800) -> TextResult:
    result = run_command(_youtube_transcript_args(url), timeout_sec=90, max_output_chars=20000)
    if not result.ok:
        logger.warning("Transcript failed: %s", result.stderr or result.error_message)
        return TextResult(
            ok=False,
            text="",
            error_message="Transcript failed. Check summarize config.",
            raw_error=(result.stderr or result.error_message),
        )
    text = (result.stdout or "").strip()
    if not text:
        return TextResult(ok=False, text="", error_message="Transcript empty.")
    if len(text) > max_chars:
        return TextResult(
            ok=True,
            text=text[: max_chars - 3].rstrip() + "...",
            truncated=True,
        )
    return TextResult(ok=True, text=text)
