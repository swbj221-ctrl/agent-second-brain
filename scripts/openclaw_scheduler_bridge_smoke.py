"""Scheduler bridge smoke for OpenClaw heartbeat/cron integration (no aiogram)."""

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

import d_brain.integrations.heartbeat_runner as heartbeat_runner  # noqa: E402
from d_brain.integrations.openclaw_bridge import dispatch_command  # noqa: E402
from d_brain.integrations.openclaw_scheduler_adapter import build_scheduler_adapter  # noqa: E402


def emit(case: str, ok: bool, **fields: object) -> None:
    payload = {"case": case, "ok": ok}
    payload.update(fields)
    print(json.dumps(payload, ensure_ascii=True))


def fake_sidecar_action(action: str, payload: dict, user_id: str | int, source: str):
    _ = payload, user_id, source
    return SimpleNamespace(status="ok", data={"action": action}, error_code=None, error_message=None)


def main() -> int:
    failures = 0
    with tempfile.TemporaryDirectory(prefix="openclaw-scheduler-bridge-smoke-") as tmp:
        os.environ["HEARTBEAT_STATE_PATH"] = str(Path(tmp) / "heartbeat_state.json")
        os.environ["OPENAI_API_KEY"] = "smoke-openai-key"
        os.environ["MODEL_ROUTE_HEARTBEAT_PROVIDER"] = "local"
        os.environ["MODEL_ROUTE_ALLOW_LOCAL_TO_OPENAI_FALLBACK"] = "true"
        os.environ["MODEL_ROUTE_FORCE_LOCAL_UNAVAILABLE"] = "false"

        original_call = heartbeat_runner.call_sidecar_action
        heartbeat_runner.call_sidecar_action = fake_sidecar_action
        try:
            hb_output = dispatch_command("/hb now", user_id=123, source_ref="smoke:hb-now")
            hb_ok = bool(hb_output and "status=ok" in hb_output)
            emit("manual_hb_now", hb_ok, output=hb_output or "")
            if not hb_ok:
                failures += 1

            cron_output = dispatch_command(
                "/cron run heartbeat.tick",
                user_id=123,
                source_ref="smoke:cron-run",
            )
            cron_ok = bool(cron_output and "job=heartbeat.tick" in cron_output)
            emit("manual_cron_run", cron_ok, output=cron_output or "")
            if not cron_ok:
                failures += 1

            invalid_output = dispatch_command(
                "/cron run unknown.job",
                user_id=123,
                source_ref="smoke:cron-invalid",
            )
            invalid_ok = bool(invalid_output and "Использование: /cron list | /cron run <job>" in invalid_output)
            emit("invalid_cron_job", invalid_ok, output=invalid_output or "")
            if not invalid_ok:
                failures += 1

            scheduled_result = build_scheduler_adapter().run_job_scheduled("heartbeat.tick")
            scheduled_payload = scheduled_result.payload
            scheduled_ok = bool(
                scheduled_result.ok
                and scheduled_payload.get("trigger") == "scheduled_openclaw"
                and scheduled_payload.get("job") == "heartbeat.tick"
            )
            emit(
                "scheduled_callback",
                scheduled_ok,
                trigger=scheduled_payload.get("trigger"),
                job=scheduled_payload.get("job"),
                status=scheduled_payload.get("status"),
                execution_mode=scheduled_result.execution_mode,
            )
            if not scheduled_ok:
                failures += 1
        finally:
            heartbeat_runner.call_sidecar_action = original_call

    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
