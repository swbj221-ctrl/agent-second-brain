"""Smoke test for OpenClaw command dispatch via the d_brain bridge."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from d_brain.integrations.openclaw_bridge import dispatch_command_response


def _extract_plan_id(text: str) -> int | None:
    for pattern in (
        re.compile(r"event_id=(?P<id>\d+)"),
        re.compile(r"#(?P<id>\d+)"),
    ):
        match = pattern.search(text or "")
        if match:
            return int(match.group("id"))
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="OpenClaw command dispatch smoke test")
    parser.add_argument("--user-id", type=int, default=123)
    parser.add_argument("--chat-id", type=int, default=123)
    parser.add_argument("--plan-title", type=str, default="OpenClaw smoke plan")
    args = parser.parse_args()

    created_id: int | None = None
    commands = [
        "/help",
        "/ping",
        "/version",
        "/diag",
        "/diag full",
        "/status",
        "/mode",
        "/prefs",
        "/prefs brevity normal",
        "/prefs lang ru",
        "/prefs voice off",
        "/voice status",
        "/voice on",
        "/prefs voice on",
        "/plan list",
        f"/plan add {args.plan_title}",
        "/plan list",
    ]
    bad_inputs = [
        "/plan done",
        "/plan done abc",
        "/plan delete",
        "/plan delete qwe",
        "/help extra",
        "/status extra",
        "/ping extra",
        "/version extra",
        "/diag extra",
        "/prefs brevity verylong",
        "/prefs lang zz",
        "/prefs voice maybe",
        "/prefs onlyone",
        "/unknown something",
        "/plan add " + ("x" * 2500),
        "/plan add weird 👀 unicode test",
    ]
    failures = 0
    secret_tokens = ("openai_api_key", "deepgram_api_key", "telegram_bot_token", "sk-")

    idx = 0
    for cmd in commands:
        idx += 1
        source_ref = f"{args.chat_id}:{idx}"
        output = dispatch_command_response(
            cmd,
            user_id=args.user_id,
            source_ref=source_ref,
        )
        text = str(output.get("text") or "")
        if cmd.startswith("/plan add "):
            created_id = _extract_plan_id(text)
        print(
            json.dumps(
                {
                    "case": f"cmd_{idx}",
                    "command": cmd,
                    "ok": output.get("ok"),
                    "error_code": output.get("error_code"),
                    "text": text,
                    "no_secrets": all(tok not in text.lower() for tok in secret_tokens),
                },
                ensure_ascii=True,
            )
        )
        if any(tok in text.lower() for tok in secret_tokens):
            failures += 1

    if created_id is not None:
        for cmd in (f"/plan done {created_id}", f"/plan delete {created_id}"):
            idx += 1
            output = dispatch_command_response(
                cmd,
                user_id=args.user_id,
                source_ref=f"{args.chat_id}:{idx}",
            )
            print(
                json.dumps(
                    {
                        "case": f"cmd_{idx}",
                        "command": cmd,
                        "ok": output.get("ok"),
                        "error_code": output.get("error_code"),
                        "text": str(output.get("text") or ""),
                    },
                    ensure_ascii=True,
                )
            )
    else:
        print(json.dumps({"case": "plan_id_missing", "ok": False, "text": "Could not extract created plan id."}, ensure_ascii=True))
        failures += 1

    for cmd in bad_inputs:
        idx += 1
        output = dispatch_command_response(
            cmd,
            user_id=args.user_id,
            source_ref=f"{args.chat_id}:{idx}",
        )
        text = str(output.get("text") or "")
        if any(tok in text.lower() for tok in secret_tokens):
            failures += 1
        expected_usage = cmd in {"/help extra", "/status extra", "/ping extra", "/version extra", "/diag extra"}
        long_guard = cmd.startswith("/plan add ") and len(cmd) > 2200
        weird_unicode = "weird" in cmd
        row = {
            "case": f"cmd_{idx}",
            "command": cmd,
            "ok": output.get("ok"),
            "error_code": output.get("error_code"),
            "text": text,
            "no_secrets": all(tok not in text.lower() for tok in secret_tokens),
        }
        if expected_usage:
            row["usage_guard"] = "Использование:" in text
            if not row["usage_guard"]:
                failures += 1
        if long_guard:
            row["long_input_guard"] = "Слишком длинная команда" in text
            if not row["long_input_guard"]:
                failures += 1
        if weird_unicode:
            row["unicode_nonfatal"] = isinstance(text, str) and len(text) > 0
            if not row["unicode_nonfatal"]:
                failures += 1
        print(
            json.dumps(row, ensure_ascii=True)
        )
    print(json.dumps({"case": "summary", "ok": failures == 0, "failures": failures}, ensure_ascii=True))
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
