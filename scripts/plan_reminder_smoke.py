"""Stage 3 plans/reminders smoke test."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


def ensure_src_on_path() -> None:
    root = Path(__file__).resolve().parents[1]
    src = root / "src"
    if src.exists() and str(src) not in sys.path:
        sys.path.insert(0, str(src))


ensure_src_on_path()

import sqlite3  # noqa: E402

from d_brain.config import get_settings  # noqa: E402
from d_brain.sidecar.dispatcher import handle_request  # noqa: E402


def make_request(action: str, payload: dict | None) -> dict:
    return handle_request(
        {
            "request_id": f"smoke-{action}",
            "user_id": "smoke-user",
            "action": action,
            "payload": payload or {},
            "metadata": {"source": "stage3-smoke"},
        }
    )


def assert_ok(response: dict, label: str) -> dict:
    if response.get("status") != "ok":
        raise AssertionError(f"{label} failed: {json.dumps(response, indent=2)}")
    return response


def run_plan_reminder_smoke() -> None:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    start_at = (now + timedelta(hours=2)).isoformat()

    create_response = assert_ok(
        make_request(
            "event_create",
            {
                "title": "Stage 3 smoke event",
                "start_at": start_at,
                "source_type": "smoke",
                "source_ref": "local",
            },
        ),
        "event_create",
    )
    event_id = create_response["data"]["event_id"]
    reminder_id = create_response["data"]["reminder_id"]
    remind_at = create_response["data"]["remind_at"]

    list_response = assert_ok(
        make_request("event_list", {"limit": 5}),
        "event_list",
    )
    events = list_response["data"]["events"]
    if not events:
        raise AssertionError("event_list returned zero events")

    reminder_list = assert_ok(
        make_request("reminder_list", {"limit": 5}),
        "reminder_list",
    )
    reminders = reminder_list["data"]["reminders"]
    if not reminders:
        raise AssertionError("reminder_list returned zero reminders")

    trigger_response = assert_ok(
        make_request("reminder_trigger_due", None),
        "reminder_trigger_due",
    )

    print("stage3_smoke_ok")
    print(f"event_id={event_id}")
    print(f"reminder_id={reminder_id}")
    print(f"remind_at={remind_at}")
    print(f"events_listed={len(events)}")
    print(f"reminders_listed={len(reminders)}")
    print(f"triggered={trigger_response['data']['triggered']}")


def run_parse_smoke() -> None:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    parse_at = (now + timedelta(hours=3)).isoformat()
    parse_text = f"Stage 3 parse smoke | {parse_at}"

    parse_response = assert_ok(
        make_request(
            "event_parse",
            {
                "text": parse_text,
                "source_type": "smoke",
                "source_ref": "parse-local",
            },
        ),
        "event_parse",
    )

    create_response = assert_ok(
        make_request(
            "event_create",
            {
                "title": parse_response["data"]["title"],
                "start_at": parse_response["data"]["start_at"],
                "remind_at": parse_response["data"]["remind_at"],
                "source_type": "smoke",
                "source_ref": "parse-local",
            },
        ),
        "event_create_from_parse",
    )

    settings = get_settings()
    with sqlite3.connect(settings.db_path) as conn:
        parse_logs = conn.execute(
            "SELECT COUNT(*) FROM event_parse_logs;"
        ).fetchone()[0]
    if parse_logs < 1:
        raise AssertionError("event_parse_logs has no rows")

    print("stage3_parse_smoke_ok")
    print(f"parsed_title={parse_response['data']['title']}")
    print(f"parsed_start_at={parse_response['data']['start_at']}")
    print(f"parsed_remind_at={parse_response['data']['remind_at']}")
    print(f"parsed_event_id={create_response['data']['event_id']}")
    print(f"parsed_reminder_id={create_response['data']['reminder_id']}")
    print(f"parse_logs={parse_logs}")


def main() -> None:
    mode = os.getenv("STAGE3_SMOKE_MODE", "all").strip().lower()
    if mode in {"all", "plan", "reminder"}:
        run_plan_reminder_smoke()
    if mode in {"all", "parse"}:
        run_parse_smoke()


if __name__ == "__main__":
    main()
