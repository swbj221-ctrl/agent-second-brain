"""Smoke checks for bridge duplicate guard (command + voice entrypoints)."""

from __future__ import annotations

import json
import time

from d_brain.integrations.openclaw_bridge import dispatch_command_response, dispatch_voice_sync
from d_brain.services.sidecar_client import call_sidecar_action


def _count_title(user_id: int, title: str) -> int:
    result = call_sidecar_action(
        "event_list",
        {"limit": 200, "offset": 0},
        user_id,
        source="duplicate_smoke",
    )
    if result.status != "ok":
        return -1
    events = (result.data or {}).get("events", [])
    return sum(1 for e in events if str(e.get("title") or "") == title)


def main() -> int:
    user_id = 123
    source_ref = "dup-smoke:123:1"
    unique_title = f"dup-smoke-{int(time.time())}"

    before_count = _count_title(user_id, unique_title)
    first = dispatch_command_response(
        f"/plan add {unique_title}",
        user_id=user_id,
        source_ref=source_ref,
    )
    second = dispatch_command_response(
        f"/plan add {unique_title}",
        user_id=user_id,
        source_ref=source_ref,
    )
    after_count = _count_title(user_id, unique_title)

    command_ok = (
        before_count >= 0
        and after_count == before_count + 1
        and bool(first.get("ok"))
        and bool(second.get("ok"))
        and bool((second.get("meta") or {}).get("duplicate_skipped"))
        and str(first.get("text") or "") == str(second.get("text") or "")
    )
    print(
        json.dumps(
            {
                "case": "command_duplicate_plan_add",
                "ok": command_ok,
                "before_count": before_count,
                "after_count": after_count,
                "duplicate_skipped": bool((second.get("meta") or {}).get("duplicate_skipped")),
                "text_equal": str(first.get("text") or "") == str(second.get("text") or ""),
            },
            ensure_ascii=True,
        )
    )

    voice_first = dispatch_voice_sync(
        user_id=user_id,
        source_ref="dup-voice:123:1",
        message_text="Transcript: duplicate smoke",
        media_declared=False,
    )
    voice_second = dispatch_voice_sync(
        user_id=user_id,
        source_ref="dup-voice:123:1",
        message_text="Transcript: duplicate smoke",
        media_declared=False,
    )
    voice_ok = bool((voice_second.get("meta") or {}).get("duplicate_skipped"))
    print(
        json.dumps(
            {
                "case": "voice_duplicate_entry",
                "ok": voice_ok,
                "handled_first": bool(voice_first.get("handled")),
                "handled_second": bool(voice_second.get("handled")),
                "duplicate_skipped": bool((voice_second.get("meta") or {}).get("duplicate_skipped")),
            },
            ensure_ascii=True,
        )
    )
    return 0 if (command_ok and voice_ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())

