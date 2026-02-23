"""Stage 4 English MVP smoke test."""

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
            "request_id": f"stage4-{action}",
            "user_id": "smoke-user",
            "action": action,
            "payload": payload or {},
            "metadata": {"source": "stage4-smoke"},
        }
    )


def assert_ok(response: dict, label: str) -> dict:
    if response.get("status") != "ok":
        raise AssertionError(f"{label} failed: {json.dumps(response, indent=2)}")
    return response


def run_stage4_smoke() -> None:
    word_response = assert_ok(
        make_request("english_word_add", {"word": "example"}),
        "english_word_add",
    )
    word_id = word_response["data"]["word_id"]

    word_list = assert_ok(
        make_request("english_word_list", {"limit": 5}),
        "english_word_list",
    )
    words = word_list["data"]["words"]
    if not words:
        raise AssertionError("english_word_list returned zero words")

    topic_response = assert_ok(
        make_request("english_topic_add", {"name": "Travel"}),
        "english_topic_add",
    )
    topic_id = topic_response["data"]["topic_id"]

    topic_list = assert_ok(
        make_request("english_topic_list", {"limit": 5}),
        "english_topic_list",
    )
    topics = topic_list["data"]["topics"]
    if not topics:
        raise AssertionError("english_topic_list returned zero topics")

    session_response = assert_ok(
        make_request("english_session_create", {"topic_id": topic_id}),
        "english_session_create",
    )
    session_id = session_response["data"]["session_id"]

    turn_user = assert_ok(
        make_request(
            "english_session_turn_append",
            {"session_id": session_id, "role": "user", "content": "Hello!"},
        ),
        "english_session_turn_append_user",
    )
    turn_assistant = assert_ok(
        make_request(
            "english_session_turn_append",
            {"session_id": session_id, "role": "assistant", "content": "Hi there."},
        ),
        "english_session_turn_append_assistant",
    )

    close_response = assert_ok(
        make_request("english_session_close", {"session_id": session_id}),
        "english_session_close",
    )

    settings = get_settings()
    with sqlite3.connect(settings.db_path) as conn:
        row = conn.execute(
            "SELECT status, summary_text FROM english_sessions WHERE id = ?;",
            (session_id,),
        ).fetchone()
        turn_count = conn.execute(
            "SELECT COUNT(*) FROM english_session_turns WHERE session_id = ?;",
            (session_id,),
        ).fetchone()[0]

    if not row:
        raise AssertionError("english_sessions row missing")
    if row[0] != "closed":
        raise AssertionError("english_sessions status is not closed")
    if not row[1]:
        raise AssertionError("english_sessions summary_text is empty")
    if turn_count < 2:
        raise AssertionError("english_session_turns has fewer than 2 turns")

    print("stage4_smoke_ok")
    print(f"word_id={word_id}")
    print(f"topic_id={topic_id}")
    print(f"session_id={session_id}")
    print(f"turn_user_id={turn_user['data']['turn_id']}")
    print(f"turn_assistant_id={turn_assistant['data']['turn_id']}")
    print(f"summary_text={close_response['data']['summary_text']}")
    print(f"words_listed={len(words)}")
    print(f"topics_listed={len(topics)}")
    print(f"turns_listed={turn_count}")


if __name__ == "__main__":
    run_stage4_smoke()
