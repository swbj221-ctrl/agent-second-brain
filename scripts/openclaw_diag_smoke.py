"""Smoke checks for bridge /diag and /diag full commands (no Telegram)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from d_brain.integrations.openclaw_bridge import dispatch_command_response


def _run_cmd(user_id: int, source_ref: str, text: str) -> dict:
    out = dispatch_command_response(text, user_id=user_id, source_ref=source_ref)
    body = str(out.get("text") or "")
    return {
        "command": text,
        "ok": bool(out.get("ok")),
        "error_code": out.get("error_code"),
        "text": body,
    }


def main() -> int:
    user_id = 505
    cases = [
        _run_cmd(user_id, "diag-smoke:1", "/diag"),
        _run_cmd(user_id, "diag-smoke:2", "/diag full"),
    ]
    failures = 0
    for idx, row in enumerate(cases, start=1):
        text = row["text"]
        if row["command"] == "/diag":
            row["has_transport"] = "transport: openclaw" in text
            row["has_sidecar"] = "sidecar:" in text
            row["has_prefs"] = "prefs:" in text
            row["has_uptime"] = "uptime_s:" in text
            ok = row["ok"] and row["has_transport"] and row["has_sidecar"] and row["has_prefs"] and row["has_uptime"]
        else:
            row["has_commit"] = "commit:" in text
            row["has_recent_errors"] = "recent_errors:" in text
            row["has_process_start"] = "process_start:" in text
            row["has_timeouts"] = "timeouts_s:" in text
            # no secret-like labels should be present
            row["no_secrets"] = all(token not in text.lower() for token in ["api_key", "token=", "openai_api_key", "deepgram_api_key"])
            ok = row["ok"] and row["has_commit"] and row["has_recent_errors"] and row["has_process_start"] and row["has_timeouts"] and row["no_secrets"]
        row["case"] = f"diag_{idx}"
        row["pass"] = ok
        if not ok:
            failures += 1
        print(json.dumps(row, ensure_ascii=True))
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
