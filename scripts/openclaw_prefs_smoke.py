"""Smoke checks for bridge-level per-user preferences."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from d_brain.integrations.openclaw_bridge import dispatch_command_response


def _run_cmd(user_id: int, idx: int, text: str) -> dict:
    out = dispatch_command_response(text, user_id=user_id, source_ref=f"prefs-smoke:{idx}")
    return {
        "command": text,
        "ok": bool(out.get("ok")),
        "error_code": out.get("error_code"),
        "text": str(out.get("text") or ""),
    }


def main() -> int:
    user_id = 4242
    commands = [
        "/prefs",
        "/prefs brevity normal",
        "/prefs lang en_tutor",
        "/prefs voice off",
        "/prefs",
        "/voice on",
        "/prefs",
    ]
    failures = 0
    last_text = ""
    for idx, cmd in enumerate(commands, start=1):
        row = _run_cmd(user_id, idx, cmd)
        last_text = row["text"]
        if not row["ok"] and cmd not in {"/prefs"}:
            failures += 1
        print(json.dumps({"case": f"cmd_{idx}", **row}, ensure_ascii=True))

    final_ok = (
        "en_tutor" in last_text
        and "normal" in last_text
        and "voice: on" in last_text
    )
    print(json.dumps({"case": "final_state", "ok": final_ok, "text": last_text}, ensure_ascii=True))
    return 0 if failures == 0 and final_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
