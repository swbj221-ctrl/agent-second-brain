"""Deterministic smoke test for OpenClaw heartbeat/cron bridge commands (no aiogram)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace


def ensure_src_on_path() -> None:
    root = Path(__file__).resolve().parents[1]
    src = root / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))


ensure_src_on_path()

import d_brain.integrations.openclaw_bridge as bridge  # noqa: E402


class FakeAdapter:
    def list_jobs(self) -> list[dict[str, object]]:
        return [{"name": "heartbeat.tick", "enabled": True}]

    def run_job_now(self, job_name: str, **kwargs):
        _ = kwargs
        if job_name != "heartbeat.tick":
            return SimpleNamespace(
                ok=False,
                status="error",
                payload={"job": job_name, "error": "job_not_registered"},
            )
        return SimpleNamespace(
            ok=True,
            status="ok",
            payload={
                "ok": True,
                "status": "ok",
                "job": "heartbeat.tick",
                "provider": "local",
                "fallback_used": False,
            },
        )


def emit(case: str, command: str, output: str | None, ok: bool) -> None:
    print(
        json.dumps(
            {
                "case": case,
                "command": command,
                "ok": ok,
                "output": output or "",
            },
            ensure_ascii=True,
        )
    )


def main() -> int:
    failures = 0

    original_build_scheduler_adapter = bridge.build_scheduler_adapter
    original_get_hb_status = bridge.get_heartbeat_status

    bridge.build_scheduler_adapter = lambda: FakeAdapter()
    bridge.get_heartbeat_status = lambda: {
        "last_run_at": "2026-02-24T10:00:00+00:00",
        "last_status": "ok",
        "last_provider": "local",
        "last_model": "utility:heuristic",
        "last_fallback_used": False,
        "last_trigger": "manual_bridge",
        "last_job_name": "heartbeat.tick",
        "last_duration_ms": 17,
        "last_error": "",
    }

    try:
        cases = [
            ("hb_now", "/hb now", lambda output: bool(output and "status=ok" in output)),
            (
                "hb_status",
                "/hb status",
                lambda output: bool(output and "last_job_name=heartbeat.tick" in output),
            ),
            (
                "cron_list",
                "/cron list",
                lambda output: bool(output and "heartbeat.tick" in output),
            ),
            (
                "cron_run_ok",
                "/cron run heartbeat.tick",
                lambda output: bool(output and "job=heartbeat.tick" in output),
            ),
            (
                "cron_run_unknown",
                "/cron run unknown.job",
                lambda output: bool(output and "/cron run <job>" in output and "/cron sync" in output),
            ),
            (
                "cron_run_usage",
                "/cron run",
                lambda output: bool(output and "/cron run <job>" in output),
            ),
            (
                "hb_usage",
                "/hb something",
                lambda output: bool(output and "/hb now" in output),
            ),
        ]

        for case, command, checker in cases:
            output = bridge.dispatch_command(command, user_id=123, source_ref=f"smoke:{case}")
            ok = checker(output)
            emit(case, command, output, ok)
            if not ok:
                failures += 1
    finally:
        bridge.build_scheduler_adapter = original_build_scheduler_adapter
        bridge.get_heartbeat_status = original_get_hb_status

    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
