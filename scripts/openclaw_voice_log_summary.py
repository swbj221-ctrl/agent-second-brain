"""Operator helper: summarize Telegram voice STT source-selection logs by requestId."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

EVENTS = {"telegram_stt_source_select", "telegram_voice_ingest"}


def _read_tail_lines_from_file(path: Path, max_lines: int) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        raise RuntimeError(f"file_read_failed:{path}:{exc}") from exc
    lines = text.splitlines()
    return lines[-max_lines:] if max_lines > 0 else lines


def _read_tail_lines_from_openclaw(max_lines: int) -> list[str]:
    cmd = ["openclaw", "logs", "--tail", str(max_lines)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore", check=False)
    except FileNotFoundError as exc:
        raise RuntimeError("openclaw_not_found") from exc
    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        raise RuntimeError(f"openclaw_logs_failed:{stderr[:200]}")
    return (proc.stdout or "").splitlines()


def _parse_events(lines: list[str]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for raw in lines:
        raw = raw.strip()
        if not raw:
            continue
        start = raw.find("{")
        if start < 0:
            continue
        try:
            obj = json.loads(raw[start:])
        except Exception:
            continue
        if str(obj.get("event") or "") in EVENTS:
            items.append(obj)
    return items


def _group_summary(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    seq = 0
    for ev in events:
        seq += 1
        request_id = str(ev.get("requestId") or "")
        if not request_id:
            request_id = f"no_request_id:{seq}"
        row = grouped.setdefault(
            request_id,
            {
                "requestId": request_id,
                "userIdHash": str(ev.get("userIdHash") or ""),
                "messageKind": str(ev.get("messageKind") or ""),
                "finalInputSource": "",
                "downloadAttempted": None,
                "downloadOk": None,
                "sttAttempted": None,
                "sttOk": None,
                "finalOutcome": "",
                "fallbackReason": "",
                "responseMode": "",
                "durationMs": None,
                "_last_seq": seq,
            },
        )
        row["_last_seq"] = seq
        if ev.get("userIdHash"):
            row["userIdHash"] = ev.get("userIdHash")
        if ev.get("messageKind"):
            row["messageKind"] = ev.get("messageKind")
        for key in ("finalInputSource", "finalOutcome", "fallbackReason", "responseMode"):
            value = str(ev.get(key) or "")
            if value:
                row[key] = value
        for key in ("downloadAttempted", "downloadOk", "sttAttempted", "sttOk", "durationMs"):
            if key in ev and ev.get(key) is not None:
                row[key] = ev.get(key)
    result = sorted(grouped.values(), key=lambda x: x.get("_last_seq", 0))
    for row in result:
        row.pop("_last_seq", None)
    return result


def _print_table(rows: list[dict[str, Any]]) -> None:
    if not rows:
        print("no_events")
        return
    headers = [
        "requestId",
        "messageKind",
        "finalInputSource",
        "downloadAttempted",
        "downloadOk",
        "sttAttempted",
        "sttOk",
        "finalOutcome",
        "fallbackReason",
        "responseMode",
        "durationMs",
    ]
    widths = {h: len(h) for h in headers}
    for row in rows:
        for h in headers:
            widths[h] = max(widths[h], len(str(row.get(h, ""))))
    print(" | ".join(h.ljust(widths[h]) for h in headers))
    print("-+-".join("-" * widths[h] for h in headers))
    for row in rows:
        print(" | ".join(str(row.get(h, "")).ljust(widths[h]) for h in headers))


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize telegram voice STT logs by requestId")
    parser.add_argument("--file", dest="file_path", default="", help="Path to log file (optional)")
    parser.add_argument("--lines", type=int, default=200, help="Tail line count (default: 200)")
    parser.add_argument("--jsonl", action="store_true", help="Print JSONL summary instead of table")
    args = parser.parse_args()

    try:
        if args.file_path:
            lines = _read_tail_lines_from_file(Path(args.file_path), max_lines=max(args.lines, 1))
        else:
            lines = _read_tail_lines_from_openclaw(max_lines=max(args.lines, 1))
    except RuntimeError as exc:
        print(str(exc))
        return 1

    events = _parse_events(lines)
    rows = _group_summary(events)
    if args.jsonl:
        for row in rows:
            print(json.dumps(row, ensure_ascii=True))
    else:
        _print_table(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
