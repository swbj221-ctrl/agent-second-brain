"""Tiny smoke for openclaw_live_voice_path_verdict.py."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / ".venv" / "Scripts" / "python.exe"
SCRIPT = ROOT / "scripts" / "openclaw_live_voice_path_verdict.py"


def _run_case(name: str, *, log_text: str, session_text: str, expected_verdict: str) -> int:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        log_path = tmp / "log.jsonl"
        session_path = tmp / "session.jsonl"
        log_path.write_text(log_text, encoding="utf-8")
        session_path.write_text(session_text, encoding="utf-8")
        proc = subprocess.run(
            [
                str(PY),
                str(SCRIPT),
                "--log-capture",
                str(log_path),
                "--session-jsonl",
                str(session_path),
                "--json",
            ],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        try:
            payload = json.loads(proc.stdout.strip() or "{}")
        except json.JSONDecodeError:
            payload = {}
        ok = payload.get("verdict") == expected_verdict
        print(
            json.dumps(
                {
                    "case": name,
                    "ok": ok,
                    "expected_verdict": expected_verdict,
                    "actual_verdict": payload.get("verdict"),
                    "returncode": proc.returncode,
                },
                ensure_ascii=True,
            )
        )
        return 0 if ok else 1


def main() -> int:
    failures = 0

    # Focused strict-proof case: requestId contains `|` (runtime style) and markers are nested in top-level log `raw`.
    rid = "oc-call_abc123|fc_def456"
    nested_lines = [
        {"event": "openclaw_voice_dispatch_path_select", "traceStage": "runtime.exec_guard", "selectedPath": "wrapper_cli_bridge", "requestId": rid},
        {"event": "openclaw_voice_dispatch_path_select", "traceStage": "redirect.path_select", "selectedPath": "wrapper_cli_bridge", "requestId": rid},
        {"event": "openclaw_voice_dispatch_path_select", "traceStage": "wrapper.path_select", "selectedPath": "d_brain_openclaw_bridge", "requestId": rid},
        {"event": "openclaw_voice_dispatch_wrapper_trace", "traceStage": "wrapper.adapter_dispatch", "requestId": rid},
        {"event": "openclaw_voice_dispatch_path_select", "traceStage": "adapter.pre_bridge", "selectedPath": "d_brain_openclaw_bridge", "request_id": rid},
        {"event": "telegram_voice_pipeline", "stage": "stt_multipass_start", "requestId": rid},
        {"event": "telegram_voice_pipeline", "stage": "stt_multipass_selected", "selectedLang": "ru", "candidateTranslitLikeLatin": False, "transcriptPreview": "Привет, how are you, ты меня понимаешь?", "request_id": rid},
        {"event": "openclaw_voice_dispatch_path_result", "traceStage": "adapter.post_bridge", "request_id": rid},
    ]
    case_focus_ok_log = "\n".join(
        json.dumps(
            {
                "type": "log",
                "subsystem": "agent/embedded",
                "message": "embedded marker",
                "raw": json.dumps(line, ensure_ascii=False),
            },
            ensure_ascii=False,
        )
        for line in nested_lines
    )
    failures += _run_case(
        "strict_chain_nested_raw_with_pipe_request_id",
        log_text=case_focus_ok_log,
        session_text='{"type":"message","message":{"role":"user","content":[{"type":"text","text":"<media:audio>"}]}}',
        expected_verdict="LIVE_PATH_CONFIRMED_BRIDGE",
    )

    case_focus_missing_stage_lines = [line for line in nested_lines if not (line.get("traceStage") == "adapter.post_bridge")]
    case_focus_missing_stage_log = "\n".join(
        json.dumps(
            {"type": "log", "message": "embedded marker", "raw": json.dumps(line, ensure_ascii=False)},
            ensure_ascii=False,
        )
        for line in case_focus_missing_stage_lines
    )
    failures += _run_case(
        "strict_chain_missing_stage_stays_inconclusive",
        log_text=case_focus_missing_stage_log,
        session_text='{"type":"message","message":{"role":"user","content":[{"type":"text","text":"<media:audio>"}]}}',
        expected_verdict="INCONCLUSIVE",
    )

    case_a_log = "\n".join(
        [
            '{"event":"openclaw_voice_dispatch_path_select","traceStage":"runtime.exec_guard","selectedPath":"wrapper_cli_bridge","requestId":"oc-123"}',
            '{"event":"openclaw_voice_dispatch_path_select","traceStage":"redirect.path_select","selectedPath":"wrapper_cli_bridge","requestId":"oc-123"}',
            '{"event":"openclaw_voice_dispatch_path_select","traceStage":"wrapper.path_select","selectedPath":"d_brain_openclaw_bridge","requestId":"oc-123"}',
            '{"event":"openclaw_voice_dispatch_wrapper_trace","traceStage":"wrapper.adapter_dispatch","requestId":"oc-123"}',
            '{"event":"openclaw_voice_dispatch_path_select","traceStage":"adapter.pre_bridge","selectedPath":"d_brain_openclaw_bridge","requestId":"oc-123"}',
            '{"event":"openclaw_voice_dispatch_path_result","traceStage":"adapter.post_bridge","requestId":"oc-123"}',
            '{"event":"telegram_voice_pipeline","stage":"stt_multipass_start","requestId":"oc-123"}',
            '{"event":"telegram_voice_pipeline","stage":"stt_multipass_selected","selectedLang":"ru","candidateTranslitLikeLatin":false,"transcriptPreview":"Привет, how are you, ты меня понимаешь?","requestId":"oc-123"}',
        ]
    )
    case_a_session = '{"type":"message","message":{"role":"assistant","content":[{"type":"text","text":"ok"}]}}'
    failures += _run_case(
            "bridge_confirmed_from_log_markers",
            log_text=case_a_log,
            session_text=case_a_session,
            expected_verdict="LIVE_PATH_CONFIRMED_BRIDGE",
    )

    # PowerShell Tee-Object often writes UTF-16LE logs; parser must still discover chain markers.
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        log_path = tmp / "log_utf16.jsonl"
        session_path = tmp / "session.jsonl"
        log_path.write_bytes(case_a_log.encode("utf-16-le"))
        session_path.write_text(case_a_session, encoding="utf-8")
        proc = subprocess.run(
            [str(PY), str(SCRIPT), "--log-capture", str(log_path), "--session-jsonl", str(session_path), "--json"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        try:
            payload = json.loads(proc.stdout.strip() or "{}")
        except json.JSONDecodeError:
            payload = {}
        ok = payload.get("verdict") == "LIVE_PATH_CONFIRMED_BRIDGE"
        print(
            json.dumps(
                {
                    "case": "bridge_confirmed_from_utf16_log_capture",
                    "ok": ok,
                    "actual_verdict": payload.get("verdict"),
                    "returncode": proc.returncode,
                },
                ensure_ascii=True,
            )
        )
        failures += 0 if ok else 1

    # Anti-contamination: full chain exists only in session history (fixture-like), not in provided log-capture.
    case_contam_log = '{"event":"telegram_voice_pipeline","stage":"stt_multipass_start","requestId":"live-req-1"}'
    case_contam_session = "\n".join(
        [
            '{"event":"openclaw_voice_dispatch_path_select","traceStage":"runtime.exec_guard","selectedPath":"wrapper_cli_bridge","requestId":"oc-call_abc123|fc_def456"}',
            '{"event":"openclaw_voice_dispatch_path_select","traceStage":"redirect.path_select","selectedPath":"wrapper_cli_bridge","requestId":"oc-call_abc123|fc_def456"}',
            '{"event":"openclaw_voice_dispatch_path_select","traceStage":"wrapper.path_select","selectedPath":"d_brain_openclaw_bridge","requestId":"oc-call_abc123|fc_def456"}',
            '{"event":"openclaw_voice_dispatch_wrapper_trace","traceStage":"wrapper.adapter_dispatch","requestId":"oc-call_abc123|fc_def456"}',
            '{"event":"openclaw_voice_dispatch_path_select","traceStage":"adapter.pre_bridge","selectedPath":"d_brain_openclaw_bridge","request_id":"oc-call_abc123|fc_def456"}',
            '{"event":"telegram_voice_pipeline","stage":"stt_multipass_selected","requestId":"oc-call_abc123|fc_def456"}',
            '{"event":"openclaw_voice_dispatch_path_result","traceStage":"adapter.post_bridge","request_id":"oc-call_abc123|fc_def456"}',
        ]
    )
    failures += _run_case(
        "session_only_fixture_chain_does_not_confirm_live",
        log_text=case_contam_log,
        session_text=case_contam_session,
        expected_verdict="INCONCLUSIVE",
    )

    # Deepgram stale history should not flip session_deepgram_direct=true if it is not tied to the live log requestId.
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        log_path = tmp / "log.jsonl"
        session_path = tmp / "session.jsonl"
        log_path.write_text(case_a_log, encoding="utf-8")
        session_path.write_text(
            "\n".join(
                [
                    '{"type":"message","message":{"role":"assistant","content":[{"type":"toolCall","name":"exec","arguments":{"command":"Invoke-RestMethod https://api.deepgram.com/v1/listen"}}]}}',
                    '{"event":"openclaw_voice_dispatch_path_select","traceStage":"runtime.exec_guard","selectedPath":"wrapper_cli_bridge","requestId":"old-req-999"}',
                ]
            ),
            encoding="utf-8",
        )
        proc = subprocess.run(
            [str(PY), str(SCRIPT), "--log-capture", str(log_path), "--session-jsonl", str(session_path), "--json"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        try:
            payload = json.loads(proc.stdout.strip() or "{}")
        except json.JSONDecodeError:
            payload = {}
        findings = payload.get("findings") or {}
        ok = payload.get("verdict") == "LIVE_PATH_CONFIRMED_BRIDGE" and findings.get("session_deepgram_direct") is False
        print(
            json.dumps(
                {
                    "case": "stale_session_deepgram_not_scoped_to_live_run",
                    "ok": ok,
                    "actual_verdict": payload.get("verdict"),
                    "session_deepgram_direct": findings.get("session_deepgram_direct"),
                    "returncode": proc.returncode,
                },
                ensure_ascii=True,
            )
        )
        failures += 0 if ok else 1

    case_b_log = "\n".join(
        [
            '{"event":"openclaw_voice_dispatch_path_select","traceStage":"runtime.exec_guard","selectedPath":"wrapper_cli_bridge","requestId":"oc-bypass-1"}',
            '{"event":"log","line":"direct deepgram probe https://api.deepgram.com/v1/listen requestId=oc-bypass-1"}',
        ]
    )
    case_b_session = "\n".join(
        [
            '{"type":"message","message":{"role":"assistant","content":[{"type":"toolCall","name":"exec","arguments":{"command":"Invoke-RestMethod https://api.deepgram.com/v1/listen"},"requestId":"oc-bypass-1"}]}}',
            '{"type":"message","message":{"role":"user","content":[{"type":"text","text":"<media:audio>"}]}}',
        ]
    )
    failures += _run_case(
        "bypass_exec_deepgram_from_session",
        log_text=case_b_log,
        session_text=case_b_session,
        expected_verdict="LIVE_PATH_BYPASS_EXEC_DEEPGRAM",
    )

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
