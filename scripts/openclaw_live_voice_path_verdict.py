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
REQUEST_ID_RE = re.compile(
    r'(?:requestId=|request_id=|\"requestId\"\s*:\s*\"|\"request_id\"\s*:\s*\")(?P<rid>[A-Za-z0-9._:\-|=+/]+)'
    r'|\\\"(?:requestId|request_id)\\\"\s*:\s*\\\"(?P<rid_esc>[A-Za-z0-9._:\-|=+/]+)'
)
TRACE_STAGE_VALUE_RE = lambda value: re.compile(  # noqa: E731
    rf'(?:traceStage=|\"traceStage\"\s*:\s*\"|\\\"traceStage\\\"\s*:\s*\\\")(?P<v>{re.escape(value)})'
)
SELECTED_PATH_VALUE_RE = lambda value: re.compile(  # noqa: E731
    rf'(?:selectedPath=|\"selectedPath\"\s*:\s*\"|\\\"selectedPath\\\"\s*:\s*\\\")(?P<v>{re.escape(value)})'
)


def _looks_like_request_id(value: str) -> bool:
    rid = str(value or "").strip()
    if not rid:
        return False
    if rid.lower() in {"true", "false", "null", "none"}:
        return False
    if len(rid) < 6:
        return False
    return True


@dataclass
class Findings:
    log_exists: bool = False
    session_exists: bool = False

    runtime_exec_guard_marker: bool = False
    wrapper_select_marker: bool = False
    wrapper_selected_bridge: bool = False
    wrapper_trace_marker: bool = False
    adapter_select_marker: bool = False  # best-effort, same marker name; differentiated heuristically
    voice_pipeline_marker: bool = False
    multipass_any_marker: bool = False
    multipass_selected_marker: bool = False
    transcript_only_fallback_marker: bool = False
    transcript_only_clarify_marker: bool = False
    bridge_path_error_marker: bool = False
    adapter_post_bridge_marker: bool = False

    selected_lang: str = ""
    selected_candidate_translit_like: bool = False
    selected_candidate_has_cyrillic: bool = False
    selected_candidate_has_latin: bool = False
    selected_transcript_preview: str = ""
    selected_transcript_mixed_scripts: bool = False

    full_chain_same_request_id: bool = False
    full_chain_request_id: str = ""
    stage_request_ids: dict[str, list[str]] = None  # type: ignore[assignment]
    stage_request_ids_log: dict[str, list[str]] = None  # type: ignore[assignment]
    required_chain_stage_sources: dict[str, str] = None  # type: ignore[assignment]
    required_chain_missing_in_log_capture: list[str] = None  # type: ignore[assignment]
    log_request_ids: list[str] = None  # type: ignore[assignment]
    log_raw_request_ids: list[str] = None  # type: ignore[assignment]
    full_chain_request_id_in_log_capture: bool = False

    session_exec_toolcall: bool = False
    session_deepgram_direct: bool = False
    session_media_audio_hint: bool = False
    scoped_deepgram_direct_log: bool = False
    scoped_deepgram_direct_session_same_request: bool = False

    evidence_lines: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.evidence_lines is None:
            self.evidence_lines = []
        if self.stage_request_ids is None:
            self.stage_request_ids = {}
        if self.stage_request_ids_log is None:
            self.stage_request_ids_log = {}
        if self.required_chain_stage_sources is None:
            self.required_chain_stage_sources = {}
        if self.required_chain_missing_in_log_capture is None:
            self.required_chain_missing_in_log_capture = []
        if self.log_request_ids is None:
            self.log_request_ids = []
        if self.log_raw_request_ids is None:
            self.log_raw_request_ids = []


def _iter_lines(path: Path) -> Iterable[str]:
    data = path.read_bytes()
    text = ""
    # `openclaw logs --follow --json --plain | Tee-Object ...` on PowerShell can
    # produce UTF-16LE output. Decode heuristically so marker scans don't silently
    # miss zero-delimited content.
    if data.startswith(b"\xff\xfe") or data.startswith(b"\xfe\xff"):
        text = data.decode("utf-16", errors="ignore")
    else:
        utf8_text = data.decode("utf-8", errors="ignore")
        if utf8_text.count("\x00") > max(8, len(utf8_text) // 32):
            try:
                text = data.decode("utf-16-le", errors="ignore")
            except Exception:
                text = utf8_text.replace("\x00", "")
        else:
            text = utf8_text
    for line in text.splitlines():
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


def _iter_obj_blobs(obj: dict) -> Iterable[str]:
    # Base flattened view
    yield _extract_text_blob(obj)

    # Common nested text-bearing fields in openclaw logs (`message`, `raw`, `text`, etc.).
    for key in ("raw", "message", "msg", "text", "line"):
        val = obj.get(key)
        if not isinstance(val, str):
            continue
        yield val
        nested = _try_parse_json(val)
        if nested is not None:
            yield _extract_text_blob(nested)
            yield json.dumps(nested, ensure_ascii=False)

    # Fallback full decoded JSON dump catches nested `requestId` in structured payloads.
    yield json.dumps(obj, ensure_ascii=False)


def _mark(findings: Findings, line: str, source: str) -> None:
    s = line
    request_id_match = REQUEST_ID_RE.search(s)
    request_id = ""
    if request_id_match:
        request_id = str(request_id_match.group("rid") or request_id_match.group("rid_esc") or "")
        if not _looks_like_request_id(request_id):
            request_id = ""
        if source.startswith("log-") and request_id and request_id not in findings.log_request_ids:
            findings.log_request_ids.append(request_id)
        if source == "log-raw" and request_id and request_id not in findings.log_raw_request_ids:
            findings.log_raw_request_ids.append(request_id)

    def _track(stage_name: str) -> None:
        if not request_id:
            return
        bucket = findings.stage_request_ids.setdefault(stage_name, [])
        if request_id not in bucket:
            bucket.append(request_id)
        if source.startswith("log-"):
            bucket_log = findings.stage_request_ids_log.setdefault(stage_name, [])
            if request_id not in bucket_log:
                bucket_log.append(request_id)

    # Generic markers
    if BRIDGE_ERROR_MARKER in s:
        findings.bridge_path_error_marker = True
        findings.evidence_lines.append(f"[{source}] {s[:500]}")

    if BRIDGE_WRAPPER_MARKER in s:
        findings.wrapper_select_marker = True
        findings.evidence_lines.append(f"[{source}] {s[:500]}")
        if TRACE_STAGE_VALUE_RE("runtime.exec_guard").search(s):
            findings.runtime_exec_guard_marker = True
            _track("runtime_exec_guard")
        if TRACE_STAGE_VALUE_RE("redirect.path_select").search(s) or "traceStage=redirect" in s:
            _track("redirect_select")
        # Distinguish wrapper/adapter best-effort by sourceModule/branchReason words
        if SELECTED_PATH_VALUE_RE("d_brain_openclaw_bridge").search(s):
            findings.wrapper_selected_bridge = True
            if TRACE_STAGE_VALUE_RE("wrapper.path_select").search(s):
                _track("wrapper_select")
        if "sourceModule=" in s or '"sourceModule"' in s:
            # likely wrapper marker
            pass
        if TRACE_STAGE_VALUE_RE("adapter.pre_bridge").search(s):
            findings.adapter_select_marker = True
            _track("adapter_pre_bridge")
    if "openclaw_voice_dispatch_path_result" in s:
        findings.adapter_post_bridge_marker = True
        findings.evidence_lines.append(f"[{source}] {s[:500]}")
        if TRACE_STAGE_VALUE_RE("adapter.post_bridge").search(s):
            _track("adapter_post_bridge")

    if "openclaw_voice_dispatch_wrapper_trace" in s:
        findings.wrapper_trace_marker = True
        findings.evidence_lines.append(f"[{source}] {s[:500]}")
        if TRACE_STAGE_VALUE_RE("wrapper.adapter_dispatch").search(s):
            _track("wrapper_trace")

    if VOICE_PIPELINE_MARKER in s:
        findings.voice_pipeline_marker = True
        findings.evidence_lines.append(f"[{source}] {s[:500]}")
        _track("telegram_voice_pipeline")
        if "stage=transcript_only_fallback" in s or '"stage":"transcript_only_fallback"' in s:
            findings.transcript_only_fallback_marker = True
        if "stage=transcript_only_clarify" in s or '"stage":"transcript_only_clarify"' in s:
            findings.transcript_only_clarify_marker = True

    if MULTIPASS_MARKER in s:
        findings.multipass_any_marker = True
        findings.evidence_lines.append(f"[{source}] {s[:500]}")
        if "stt_multipass_selected" in s:
            findings.multipass_selected_marker = True
            _track("stt_multipass_selected")
            m = re.search(r'(?:selectedLang=|\"selectedLang\":\")(?P<lang>ru|en|auto)', s)
            if m:
                findings.selected_lang = m.group("lang")
            if "candidateTranslitLikeLatin=True" in s or '"candidateTranslitLikeLatin":true' in s:
                findings.selected_candidate_translit_like = True
            if "candidateHasCyrillic=True" in s or '"candidateHasCyrillic":true' in s:
                findings.selected_candidate_has_cyrillic = True
            if "candidateHasLatin=True" in s or '"candidateHasLatin":true' in s:
                findings.selected_candidate_has_latin = True
            m_prev = re.search(r'(?:transcriptPreview=|\"transcriptPreview\":\")(?P<p>[^|]{1,240})', s)
            if m_prev:
                findings.selected_transcript_preview = m_prev.group("p")[:240].strip().strip('"')
                findings.selected_transcript_mixed_scripts = bool(
                    re.search(r"[A-Za-z]", findings.selected_transcript_preview)
                    and re.search(r"[\u0400-\u04FF]", findings.selected_transcript_preview)
                )

    # Session bypass signatures
    if re.search(r"\btool(Call)?\b", s, flags=re.IGNORECASE) and "exec" in s:
        findings.session_exec_toolcall = True
        findings.evidence_lines.append(f"[{source}] {s[:500]}")

    if DEEPGRAM_HOST_HINT in s or "deepgram.com" in s:
        findings.evidence_lines.append(f"[{source}] {s[:500]}")
        if source.startswith("log-"):
            findings.scoped_deepgram_direct_log = True
        elif source.startswith("session-"):
            if request_id and request_id in set(findings.log_request_ids):
                findings.scoped_deepgram_direct_session_same_request = True

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
            for blob in _iter_obj_blobs(obj):
                _mark(findings, blob, source="log-json")
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
            for blob in _iter_obj_blobs(obj):
                _mark(findings, blob, source="session-json")


def make_verdict(findings: Findings) -> tuple[str, str]:
    required_chain = [
        "runtime_exec_guard",
        "redirect_select",
        "wrapper_select",
        "wrapper_trace",
        "adapter_pre_bridge",
        "adapter_post_bridge",
        "telegram_voice_pipeline",
        "stt_multipass_selected",
    ]
    findings.required_chain_stage_sources = {}
    findings.required_chain_missing_in_log_capture = []
    for stage in required_chain:
        has_any = bool(findings.stage_request_ids.get(stage))
        has_log = bool(findings.stage_request_ids_log.get(stage))
        if has_log:
            findings.required_chain_stage_sources[stage] = "log_capture"
        elif has_any:
            findings.required_chain_stage_sources[stage] = "session_only"
            findings.required_chain_missing_in_log_capture.append(stage)
        else:
            findings.required_chain_stage_sources[stage] = "missing"
            findings.required_chain_missing_in_log_capture.append(stage)
    req_sets = [set(findings.stage_request_ids.get(k, [])) for k in required_chain]
    req_sets_log = [set(findings.stage_request_ids_log.get(k, [])) for k in required_chain]
    if all(req_sets):
        common = set.intersection(*req_sets)
        log_seen_ids = set(findings.log_request_ids)
        if all(req_sets_log):
            common_log = set.intersection(*req_sets_log)
        else:
            common_log = set()
        # Strict anti-contamination: confirmed bridge requestId must be present in log-capture
        # and, when possible, derived from log-capture stage markers.
        common_scoped = common_log or (common & log_seen_ids)
        if common_scoped:
            findings.full_chain_same_request_id = True
            findings.full_chain_request_id = sorted(common_scoped)[0]
            findings.full_chain_request_id_in_log_capture = (
                findings.full_chain_request_id in set(findings.log_raw_request_ids)
            )
            if not findings.full_chain_request_id_in_log_capture:
                findings.full_chain_same_request_id = False
                findings.full_chain_request_id = ""

    findings.session_deepgram_direct = bool(
        findings.scoped_deepgram_direct_log
        or findings.scoped_deepgram_direct_session_same_request
    )

    # Strong bridge confirmation
    if findings.full_chain_same_request_id and findings.wrapper_selected_bridge and findings.voice_pipeline_marker:
        if findings.multipass_selected_marker or findings.multipass_any_marker:
            return (
                "LIVE_PATH_CONFIRMED_BRIDGE",
                f"Full same-requestId chain found ({findings.full_chain_request_id}) including runtime/redirect/wrapper/adapter/bridge multipass markers.",
            )
        return (
            "LIVE_PATH_CONFIRMED_BRIDGE",
            f"Full same-requestId chain found ({findings.full_chain_request_id}) with bridge pipeline.",
        )

    if findings.wrapper_selected_bridge and findings.voice_pipeline_marker:
        if not findings.full_chain_request_id_in_log_capture and any(req_sets):
            stage_hint = ",".join(findings.required_chain_missing_in_log_capture[:4])
            return (
                "INCONCLUSIVE",
                "Bridge markers found, but the candidate chain requestId is not discoverable in the provided log-capture."
                + (f" Missing/log-misaligned stages: {stage_hint}." if stage_hint else ""),
            )
        return (
            "INCONCLUSIVE",
            "Bridge markers found, but no full same-requestId runtime->redirect->wrapper->adapter->bridge chain.",
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
    findings_json = asdict(findings)
    if show_evidence >= 0:
        findings_json["evidence_lines"] = list(findings.evidence_lines[:show_evidence])
    payload = {
        "verdict": verdict,
        "reason": reason,
        "findings": findings_json,
    }

    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    print(f"VERDICT: {verdict}")
    print(f"Reason: {reason}")
    print()
    print("Findings:")
    for k, v in findings_json.items():
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
