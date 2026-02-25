"""Scheduler config smoke for OpenClaw heartbeat/digest command controls (no aiogram)."""

from __future__ import annotations

import json
import os
import sys
import tempfile
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
    def __init__(self) -> None:
        self.synced_jobs: list[dict[str, object]] = []

    def list_jobs(self) -> list[dict[str, object]]:
        if self.synced_jobs:
            return [dict(job) for job in self.synced_jobs]
        return [
            {
                "name": "heartbeat.tick",
                "enabled": True,
                "schedule_kind": "interval_minutes",
                "schedule_value": 30,
            },
            {
                "name": "digest.daily",
                "enabled": False,
                "schedule_kind": "daily_time",
                "schedule_value": "09:30",
            },
        ]

    def sync_jobs(self, job_specs: list[dict[str, object]], *, trigger_source: str = "manual_bridge") -> dict[str, object]:
        self.synced_jobs = [dict(job) for job in job_specs]
        return {
            "ok": True,
            "status": "ok",
            "execution_mode": "stub_fallback",
            "trigger_source": trigger_source,
            "jobs": self.synced_jobs,
            "payload": {"ok": True, "status": "ok"},
        }

    def run_job_now(self, job_name: str, **kwargs):
        _ = kwargs
        return SimpleNamespace(
            ok=True,
            status="ok",
            payload={
                "ok": True,
                "status": "ok",
                "job": job_name,
                "provider": "local",
                "fallback_used": False,
            },
        )


def emit(case: str, command: str, output: str | None, ok: bool) -> None:
    print(json.dumps({"case": case, "command": command, "ok": ok, "output": output or ""}, ensure_ascii=True))


def main() -> int:
    failures = 0
    with tempfile.TemporaryDirectory(prefix="openclaw-scheduler-config-smoke-") as tmp:
        os.environ["HEARTBEAT_STATE_PATH"] = str(Path(tmp) / "heartbeat_state.json")
        os.environ["OPENAI_API_KEY"] = "smoke-openai-key"
        os.environ["MODEL_ROUTE_COMMAND_STATUS_PROVIDER"] = "deterministic"

        fake_adapter = FakeAdapter()
        original_build_adapter = bridge.build_scheduler_adapter
        bridge.build_scheduler_adapter = lambda: fake_adapter

        try:
            cases = [
                ("hb_interval_ok", "/hb interval 30", lambda out: bool(out and "interval=30" in out)),
                ("hb_off", "/hb off", lambda out: bool(out and "Heartbeat off" in out)),
                ("hb_on", "/hb on", lambda out: bool(out and "Heartbeat on" in out)),
                ("digest_time_ok", "/digest time 09:30", lambda out: bool(out and "Digest time=09:30" in out)),
                ("digest_on", "/digest on", lambda out: bool(out and "Digest on" in out)),
                ("cron_sync", "/cron sync", lambda out: bool(out and "Cron sync status=ok" in out)),
                ("cron_list", "/cron list", lambda out: bool(out and "digest.daily" in out and "heartbeat.tick" in out)),
                ("hb_interval_missing", "/hb interval", lambda out: bool(out and "/hb interval <minutes>" in out)),
                ("hb_interval_abc", "/hb interval abc", lambda out: bool(out and "/hb interval <minutes>" in out)),
                ("hb_interval_too_low", "/hb interval 1", lambda out: bool(out and "5..240" in out)),
                ("digest_time_invalid", "/digest time 25:99", lambda out: bool(out and "/digest time HH:MM" in out)),
            ]

            for case, command, check in cases:
                output = bridge.dispatch_command(command, user_id=123, source_ref=f"smoke:{case}")
                ok = check(output)
                emit(case, command, output, ok)
                if not ok:
                    failures += 1
        finally:
            bridge.build_scheduler_adapter = original_build_adapter

    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
