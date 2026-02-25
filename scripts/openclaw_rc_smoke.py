"""Release-candidate smoke suite for OpenClaw-first bridge (no Telegram polling)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _run_step(root: Path, script_rel: str, *, args: list[str] | None = None) -> tuple[bool, dict[str, object]]:
    cmd = [sys.executable, script_rel]
    if args:
        cmd.extend(args)
    env = os.environ.copy()
    env.setdefault("PYTHONPATH", "src")
    env.setdefault("D_BRAIN_TELEGRAM_DISABLED", "1")
    proc = subprocess.run(
        cmd,
        cwd=str(root),
        env=env,
        text=True,
        capture_output=True,
        timeout=120,
    )
    stdout_lines = [line for line in (proc.stdout or "").splitlines() if line.strip()]
    stderr_lines = [line for line in (proc.stderr or "").splitlines() if line.strip()]
    row: dict[str, object] = {
        "script": script_rel,
        "ok": proc.returncode == 0,
        "exit_code": proc.returncode,
        "stdout_lines": len(stdout_lines),
        "stderr_lines": len(stderr_lines),
        "stdout_tail": stdout_lines[-3:],
        "stderr_tail": stderr_lines[-3:],
    }
    return proc.returncode == 0, row


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    failures = 0
    steps: list[tuple[str, list[str] | None]] = [
        ("scripts/no_polling_when_disabled_check.py", None),
        ("scripts/prod_readiness_check.py", None),
        ("scripts/openclaw_command_dispatch_smoke.py", ["--user-id", "701", "--chat-id", "701", "--plan-title", "RC smoke plan"]),
        ("scripts/openclaw_prefs_smoke.py", None),
        ("scripts/openclaw_diag_smoke.py", None),
        ("scripts/openclaw_voice_dispatch_smoke.py", None),
        ("scripts/voice_media_preference_check.py", None),
    ]
    for script_rel, args in steps:
        try:
            ok, row = _run_step(root, script_rel, args=args)
        except subprocess.TimeoutExpired as exc:
            ok = False
            row = {
                "script": script_rel,
                "ok": False,
                "exit_code": "timeout",
                "stdout_lines": len((exc.stdout or "").splitlines()) if isinstance(exc.stdout, str) else 0,
                "stderr_lines": len((exc.stderr or "").splitlines()) if isinstance(exc.stderr, str) else 0,
                "stdout_tail": ((exc.stdout or "").splitlines()[-3:] if isinstance(exc.stdout, str) else []),
                "stderr_tail": ((exc.stderr or "").splitlines()[-3:] if isinstance(exc.stderr, str) else []),
            }
        if not ok:
            failures += 1
        print(json.dumps(row, ensure_ascii=True))

    summary = {
        "summary": {
            "ok": failures == 0,
            "status": "PASS" if failures == 0 else "FAIL",
            "steps": len(steps),
            "failed_steps": failures,
        }
    }
    print(json.dumps(summary, ensure_ascii=True))
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

