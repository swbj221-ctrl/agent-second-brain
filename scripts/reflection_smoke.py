"""Stage 5 Reflection MVP smoke test."""

from __future__ import annotations

import json
import sys
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
            "request_id": f"stage5-{action}",
            "user_id": "smoke-user",
            "action": action,
            "payload": payload or {},
            "metadata": {"source": "stage5-smoke"},
        }
    )


def assert_ok(response: dict, label: str) -> dict:
    if response.get("status") != "ok":
        raise AssertionError(f"{label} failed: {json.dumps(response, indent=2)}")
    return response


def run_stage5_smoke() -> None:
    session_response = assert_ok(
        make_request("reflection_session_create", {}),
        "reflection_session_create",
    )
    session_id = session_response["data"]["session_id"]

    turn_user = assert_ok(
        make_request(
            "reflection_turn_append",
            {"session_id": session_id, "role": "user", "content": "Today was busy."},
        ),
        "reflection_turn_append_user",
    )
    turn_assistant = assert_ok(
        make_request(
            "reflection_turn_append",
            {
                "session_id": session_id,
                "role": "assistant",
                "content": "What stood out the most?",
            },
        ),
        "reflection_turn_append_assistant",
    )

    close_response = assert_ok(
        make_request("reflection_session_close", {"session_id": session_id}),
        "reflection_session_close",
    )

    list_response = assert_ok(
        make_request("reflection_session_list", {"limit": 5}),
        "reflection_session_list",
    )
    sessions = list_response["data"]["sessions"]
    if not sessions:
        raise AssertionError("reflection_session_list returned zero sessions")

    settings = get_settings()
    with sqlite3.connect(settings.db_path) as conn:
        row = conn.execute(
            "SELECT status, summary_text FROM reflection_sessions WHERE id = ?;",
            (session_id,),
        ).fetchone()
        turn_count = conn.execute(
            "SELECT COUNT(*) FROM reflection_turns WHERE session_id = ?;",
            (session_id,),
        ).fetchone()[0]

    if not row:
        raise AssertionError("reflection_sessions row missing")
    if row[0] != "closed":
        raise AssertionError("reflection_sessions status is not closed")
    if not row[1]:
        raise AssertionError("reflection_sessions summary_text is empty")
    if turn_count < 2:
        raise AssertionError("reflection_turns has fewer than 2 turns")

    print("stage5_smoke_ok")
    print(f"session_id={session_id}")
    print(f"turn_user_id={turn_user['data']['turn_id']}")
    print(f"turn_assistant_id={turn_assistant['data']['turn_id']}")
    print(f"summary_text={close_response['data']['summary_text']}")
    print(f"sessions_listed={len(sessions)}")
    print(f"turns_listed={turn_count}")


if __name__ == "__main__":
    run_stage5_smoke()
