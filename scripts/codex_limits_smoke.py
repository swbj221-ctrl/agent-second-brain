"""Stage 8 Codex limits + economy mode advisory smoke test."""

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
            "request_id": f"stage8-{action}",
            "user_id": "smoke-user",
            "action": action,
            "payload": payload or {},
            "metadata": {"source": "stage8-smoke"},
        }
    )


def assert_ok(response: dict, label: str) -> dict:
    if response.get("status") != "ok":
        raise AssertionError(f"{label} failed: {json.dumps(response, indent=2)}")
    return response


def run_stage8_smoke() -> None:
    for idx in range(3):
        assert_ok(
            make_request(
                "codex_usage_log_add",
                {
                    "scope_key": "global",
                    "request_id": f"smoke-{idx}",
                    "user_id": "smoke-user",
                    "model_ref": "codex-test",
                    "context": "smoke",
                    "tokens_in": 500,
                    "tokens_out": 300,
                    "total_tokens": 800,
                    "latency_ms": 1200,
                    "request_count": 1,
                    "metadata": {"stage": "8"},
                },
            ),
            "codex_usage_log_add",
        )

    limits = assert_ok(
        make_request(
            "codex_limits_settings_upsert",
            {
                "scope_key": "global",
                "window_hours": 24,
                "max_tokens": 2000,
                "max_requests": 3,
                "max_latency_ms": 4000,
                "warn_ratio": 0.70,
                "critical_ratio": 0.90,
            },
        ),
        "codex_limits_settings_upsert",
    )

    status_response = assert_ok(
        make_request("codex_usage_status_get", {"scope_key": "global"}),
        "codex_usage_status_get",
    )
    status = status_response["data"]
    if status["status_level"] not in {"warn", "critical"}:
        raise AssertionError("status_level should be warn or critical")
    if status["percent_used"]["tokens"] is None:
        raise AssertionError("tokens percent_used is missing")
    if status["percent_used"]["requests"] is None:
        raise AssertionError("requests percent_used is missing")
    if status["percent_used"]["latency_ms"] is None:
        raise AssertionError("latency percent_used is missing")

    settings = get_settings()
    with sqlite3.connect(settings.db_path) as conn:
        usage_count = conn.execute(
            "SELECT COUNT(*) FROM codex_usage_logs;"
        ).fetchone()[0]
        limits_count = conn.execute(
            "SELECT COUNT(*) FROM codex_limits_settings;"
        ).fetchone()[0]

    if usage_count < 1:
        raise AssertionError("codex_usage_logs table has no rows")
    if limits_count < 1:
        raise AssertionError("codex_limits_settings table has no rows")

    print("stage8_smoke_ok")
    print(f"usage_logs={usage_count}")
    print(f"limits_rows={limits_count}")
    print(f"status_level={status['status_level']}")
    print(f"warn_ratio={status['warn_ratio']}")
    print(f"critical_ratio={status['critical_ratio']}")
    print(f"window_hours={status['window_hours']}")
    print(f"settings_id={limits['data']['settings_id']}")


if __name__ == "__main__":
    run_stage8_smoke()
