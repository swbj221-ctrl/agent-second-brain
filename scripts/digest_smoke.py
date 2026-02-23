"""Stage 7 Digest + Heartbeat smoke test."""

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
            "request_id": f"stage7-{action}",
            "user_id": "smoke-user",
            "action": action,
            "payload": payload or {},
            "metadata": {"source": "stage7-smoke"},
        }
    )


def assert_ok(response: dict, label: str) -> dict:
    if response.get("status") != "ok":
        raise AssertionError(f"{label} failed: {json.dumps(response, indent=2)}")
    return response


def run_stage7_smoke() -> None:
    heartbeat_response = assert_ok(
        make_request(
            "heartbeat_tick",
            {"event_source": "smoke", "event_details": {"purpose": "stage7_smoke"}},
        ),
        "heartbeat_tick",
    )
    heartbeat_id = heartbeat_response["data"]["heartbeat_log_id"]

    digest_response = assert_ok(
        make_request("digest_generate", {}),
        "digest_generate",
    )
    digest_id = digest_response["data"]["digest_id"]
    digest_payload = digest_response["data"]["payload"]
    if digest_payload.get("payload_version") != 1:
        raise AssertionError("digest payload_version is not 1")
    if digest_payload.get("digest_type") != "system_state":
        raise AssertionError("digest digest_type is not system_state")

    latest_response = assert_ok(
        make_request("digest_get_latest", {}),
        "digest_get_latest",
    )
    latest = latest_response["data"]
    if latest["id"] != digest_id:
        raise AssertionError("digest_get_latest did not return the latest digest")

    settings = get_settings()
    with sqlite3.connect(settings.db_path) as conn:
        digest_count = conn.execute("SELECT COUNT(*) FROM digests;").fetchone()[0]
        heartbeat_count = conn.execute(
            "SELECT COUNT(*) FROM heartbeat_logs;"
        ).fetchone()[0]

    if digest_count < 1:
        raise AssertionError("digests table has no rows")
    if heartbeat_count < 1:
        raise AssertionError("heartbeat_logs table has no rows")

    print("stage7_smoke_ok")
    print(f"heartbeat_log_id={heartbeat_id}")
    print(f"digest_id={digest_id}")
    print(f"digest_type={digest_payload.get('digest_type')}")
    print(f"digests={digest_count}")
    print(f"heartbeat_logs={heartbeat_count}")


if __name__ == "__main__":
    run_stage7_smoke()
