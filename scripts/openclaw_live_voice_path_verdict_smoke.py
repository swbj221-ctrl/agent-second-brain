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

    case_a_log = "\n".join(
        [
            '{"event":"openclaw_voice_dispatch_path_select","selectedPath":"d_brain_openclaw_bridge"}',
            '{"event":"openclaw_bridge_runtime_dispatch_entry"}',
            '{"event":"telegram_voice_pipeline","stage":"stt_multipass_start"}',
            '{"event":"telegram_voice_pipeline","stage":"stt_multipass_selected","selectedLang":"ru"}',
        ]
    )
    case_a_session = '{"type":"message","message":{"role":"assistant","content":[{"type":"text","text":"ok"}]}}'
    failures += _run_case(
        "bridge_confirmed_from_log_markers",
        log_text=case_a_log,
        session_text=case_a_session,
        expected_verdict="LIVE_PATH_CONFIRMED_BRIDGE",
    )

    case_b_log = '{"event":"unrelated"}'
    case_b_session = "\n".join(
        [
            '{"type":"message","message":{"role":"assistant","content":[{"type":"toolCall","name":"exec","arguments":{"command":"Invoke-RestMethod https://api.deepgram.com/v1/listen"}}]}}',
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
