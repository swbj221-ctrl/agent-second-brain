# -*- coding: utf-8 -*-
r"""
Best-effort verdict for live Telegram voice/audio path:
- LIVE_PATH_CONFIRMED_BRIDGE
- LIVE_PATH_BYPASS_EXEC_DEEPGRAM
- INCONCLUSIVE

Usage (PowerShell):
  .\.venv\Scripts\python.exe scripts\openclaw_live_voice_path_verdict.py `
    --log-capture .\artifacts\openclaw_logs_multipass_live_follow.jsonl `
    --session-jsonl "$env:USERPROFILE\.openclaw\agents\main\sessions\ade475a8-bd5f-4bd1-b13e-ce122383c629.jsonl"

Notes:
- Works with mixed JSONL/plain log lines (best effort).
- No external deps.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable, Optional


BRIDGE_WRAPPER_MARKER = "openclaw_voice_dispatch_path_select"
BRIDGE_ERROR_MARKER = "openclaw_voice_dispatch_path_error"
VOICE_PIPELINE_MARKER = "telegram_voice_pipeline"
MULTIPASS_MARKER = "stt_multipass_"
DEEPGRAM_HOST_HINT = "api.deepgram.com/v1/listen"


@dataclass
class Findings:
    log_exists: bool = False
    session_exists: bool = False

    wrapper_select_marker: bool = False
    wrapper_selected_bridge: bool = False
    adapter_select_marker: bool = False  # best-effort, same marker name; differentiated heuristically
    voice_pipeline_marker: bool = False
    multipass_any_marker: bool = False
    multipass_selected_marker: bool = False
    bridge_path_error_marker: bool = False

    session_exec_toolcall: bool = False
    session_deepgram_direct: bool = False
    session_media_audio_hint: bool = False

    evidence_lines: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.evidence_lines is None:
            self.evidence_lines = []


def _iter_lines(path: Path) -> Iterable[str]:
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            yield line.rstrip("\n")


def _try_parse_json(line: str) -> Optional[dict]:
    line = line.strip()
    if not line:
        return None
    if not (line.startswith("{") and line.endswith("}")):
        return None
    try:
        obj = json.loads(line)
        if isinstance(obj, dict):
            return obj
    except Exception:
        return None
    return None


def _extract_text_blob(obj: dict) -> str:
    # Best effort: combine common fields + dump fallback
    parts = []
    for key in ("event", "message", "msg", "text", "line", "subsystem"):
        val = obj.get(key)
        if isinstance(val, str):
            parts.append(val)
    # include shallow values for searches like selectedPath=...
    for k, v in obj.items():
        if isinstance(v, (str, int, float, bool)):
            parts.append(f"{k}={v}")
    if not parts:
        return json.dumps(obj, ensure_ascii=False)
    return " | ".join(parts)


def _mark(findings: Findings, line: str, source: str) -> None:
    s = line

    # Generic markers
    if BRIDGE_ERROR_MARKER in s:
        findings.bridge_path_error_marker = True
        findings.evidence_lines.append(f"[{source}] {s[:500]}")

    if BRIDGE_WRAPPER_MARKER in s:
        findings.wrapper_select_marker = True
        findings.evidence_lines.append(f"[{source}] {s[:500]}")
        # Distinguish wrapper/adapter best-effort by sourceModule/branchReason words
        if "selectedPath=d_brain_openclaw_bridge" in s or '"selectedPath":"d_brain_openclaw_bridge"' in s:
            findings.wrapper_selected_bridge = True
        if "sourceModule=" in s or '"sourceModule"' in s:
            # likely wrapper marker
            pass
        if "branchReason=media_detected_or_noncommand_text" in s or "media_detected_or_noncommand_text" in s:
            findings.adapter_select_marker = True

    if VOICE_PIPELINE_MARKER in s:
        findings.voice_pipeline_marker = True
        findings.evidence_lines.append(f"[{source}] {s[:500]}")

    if MULTIPASS_MARKER in s:
        findings.multipass_any_marker = True
        findings.evidence_lines.append(f"[{source}] {s[:500]}")
        if "stt_multipass_selected" in s:
            findings.multipass_selected_marker = True

    # Session bypass signatures
    if re.search(r"\btool(Call)?\b", s, flags=re.IGNORECASE) and "exec" in s:
        findings.session_exec_toolcall = True
        findings.evidence_lines.append(f"[{source}] {s[:500]}")

    if DEEPGRAM_HOST_HINT in s or "deepgram.com" in s:
        findings.session_deepgram_direct = True
        findings.evidence_lines.append(f"[{source}] {s[:500]}")

    if "<media:audio>" in s or "[Audio]" in s or "[media attached" in s:
        findings.session_media_audio_hint = True


def scan_log_capture(path: Optional[Path], findings: Findings) -> None:
    if not path:
        return
    if not path.exists():
        return
    findings.log_exists = True

    for raw in _iter_lines(path):
        obj = _try_parse_json(raw)
        if obj is not None:
            text = _extract_text_blob(obj)
            _mark(findings, text, source="log-json")
            # Also raw, because some JSONL embeds quoted strings differently
            _mark(findings, raw, source="log-raw")
        else:
            _mark(findings, raw, source="log-plain")


def scan_session_jsonl(path: Optional[Path], findings: Findings) -> None:
    if not path:
        return
    if not path.exists():
        return
    findings.session_exists = True

    for raw in _iter_lines(path):
        _mark(findings, raw, source="session-raw")
        obj = _try_parse_json(raw)
        if obj is not None:
            _mark(findings, _extract_text_blob(obj), source="session-json")


def make_verdict(findings: Findings) -> tuple[str, str]:
    # Strong bridge confirmation
    if findings.wrapper_selected_bridge and findings.voice_pipeline_marker:
        if findings.multipass_selected_marker or findings.multipass_any_marker:
            return (
                "LIVE_PATH_CONFIRMED_BRIDGE",
                "Wrapper bridge select marker + telegram_voice_pipeline + multipass marker(s) found.",
            )
        return (
            "LIVE_PATH_CONFIRMED_BRIDGE",
            "Wrapper bridge select marker + telegram_voice_pipeline found.",
        )

    # Bypass confirmation (especially if audio hints present)
    if findings.session_exec_toolcall and findings.session_deepgram_direct:
        if not findings.voice_pipeline_marker and not findings.wrapper_select_marker:
            return (
                "LIVE_PATH_BYPASS_EXEC_DEEPGRAM",
                "Session shows exec + direct Deepgram and bridge markers are absent.",
            )
        return (
            "LIVE_PATH_BYPASS_EXEC_DEEPGRAM",
            "Session shows exec + direct Deepgram (bridge markers incomplete/ambiguous).",
        )

    # Wrapper called but bridge unavailable
    if findings.bridge_path_error_marker and findings.wrapper_select_marker and not findings.voice_pipeline_marker:
        return (
            "INCONCLUSIVE",
            "Wrapper path markers found but bridge pipeline marker missing (possible bridge dispatch unavailable).",
        )

    return (
        "INCONCLUSIVE",
        "Not enough proof for bridge confirmation or exec+Deepgram bypass confirmation.",
    )


def print_report(findings: Findings, verdict: str, reason: str, as_json: bool = False, show_evidence: int = 12) -> None:
    payload = {
        "verdict": verdict,
        "reason": reason,
        "findings": asdict(findings),
    }

    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    print(f"VERDICT: {verdict}")
    print(f"Reason: {reason}")
    print()
    print("Findings:")
    for k, v in asdict(findings).items():
        if k == "evidence_lines":
            continue
        print(f"- {k}: {v}")

    if findings.evidence_lines:
        print()
        print(f"Evidence (first {show_evidence}):")
        for line in findings.evidence_lines[:show_evidence]:
            print(f"  - {line}")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="OpenClaw live voice path verdict (bridge vs bypass)")
    p.add_argument("--log-capture", type=str, default=None, help="Path to openclaw logs follow capture jsonl/plain")
    p.add_argument("--session-jsonl", type=str, default=None, help="Path to active/latest OpenClaw session jsonl")
    p.add_argument("--json", action="store_true", help="Print JSON report")
    p.add_argument("--evidence-limit", type=int, default=12, help="How many evidence lines to print")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    findings = Findings()
    log_path = Path(args.log_capture) if args.log_capture else None
    session_path = Path(args.session_jsonl) if args.session_jsonl else None

    scan_log_capture(log_path, findings)
    scan_session_jsonl(session_path, findings)

    verdict, reason = make_verdict(findings)
    print_report(findings, verdict, reason, as_json=args.json, show_evidence=args.evidence_limit)

    # Exit code semantics:
    # 0 = confirmed bridge
    # 2 = confirmed bypass
    # 1 = inconclusive
    if verdict == "LIVE_PATH_CONFIRMED_BRIDGE":
        return 0
    if verdict == "LIVE_PATH_BYPASS_EXEC_DEEPGRAM":
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
