"""Smoke checks for OpenClaw-first transport-agnostic job runner."""

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

import d_brain.integrations.openclaw_jobs as openclaw_jobs  # noqa: E402
from d_brain.integrations.openclaw_jobs import (  # noqa: E402
    JOB_DAILY_DIGEST,
    JOB_HEARTBEAT_SUMMARY,
    JOB_PLAN_REMINDER_DISPATCH,
    JobContext,
    run_job,
)


def emit(case: str, ok: bool, result: dict[str, object]) -> None:
    print(json.dumps({"case": case, "ok": ok, "result": result}, ensure_ascii=True))


def _fake_sidecar_no_items(action: str, payload: dict, user_id: str | int, source: str):
    _ = payload, user_id, source
    if action == "event_list":
        return SimpleNamespace(status="ok", data={"events": []}, error_code=None)
    return SimpleNamespace(status="ok", data={"action": action}, error_code=None)


def main() -> int:
    failures = 0

    # case=heartbeat_no_target
    result_heartbeat_no_target = run_job(
        JOB_HEARTBEAT_SUMMARY,
        context=JobContext(
            user_id="smoke-user",
            channel="telegram",
            target="",
            source_ref="smoke:heartbeat_no_target",
            dry_run=False,
            trigger="manual",
        ),
    )
    ok_heartbeat_no_target = bool(
        result_heartbeat_no_target.get("ok")
        and not result_heartbeat_no_target.get("executed")
        and str((result_heartbeat_no_target.get("outbound_result") or {}).get("delivery_state") or "") == "no_target"
    )
    emit("heartbeat_no_target", ok_heartbeat_no_target, result_heartbeat_no_target)
    if not ok_heartbeat_no_target:
        failures += 1

    # case=digest_dry_run
    result_digest_dry = run_job(
        JOB_DAILY_DIGEST,
        context=JobContext(
            user_id="smoke-user",
            channel="telegram",
            target="123",
            source_ref="smoke:digest_dry_run",
            dry_run=True,
            trigger="manual",
        ),
    )
    ok_digest_dry = bool(
        result_digest_dry.get("ok")
        and not result_digest_dry.get("executed")
        and result_digest_dry.get("skipped_reason") == "dry_run"
        and str((result_digest_dry.get("outbound_result") or {}).get("delivery_state") or "") == "deferred"
    )
    emit("digest_dry_run", ok_digest_dry, result_digest_dry)
    if not ok_digest_dry:
        failures += 1

    # case=plan_reminder_no_items
    original_call = openclaw_jobs.call_sidecar_action
    openclaw_jobs.call_sidecar_action = _fake_sidecar_no_items
    try:
        result_plan_no_items = run_job(
            JOB_PLAN_REMINDER_DISPATCH,
            context=JobContext(
                user_id="smoke-user",
                channel="telegram",
                target="123",
                source_ref="smoke:plan_reminder_no_items",
                dry_run=False,
                trigger="manual",
            ),
        )
    finally:
        openclaw_jobs.call_sidecar_action = original_call
    ok_plan_no_items = bool(
        result_plan_no_items.get("ok")
        and not result_plan_no_items.get("executed")
        and result_plan_no_items.get("skipped_reason") == "no_items"
    )
    emit("plan_reminder_no_items", ok_plan_no_items, result_plan_no_items)
    if not ok_plan_no_items:
        failures += 1

    # case=outbound_fail_fallback
    def failing_sender(channel: str, target: str, text: str) -> dict[str, object]:
        _ = channel, target, text
        raise RuntimeError("smoke_sender_failure")

    result_outbound_fail = run_job(
        JOB_HEARTBEAT_SUMMARY,
        context=JobContext(
            user_id="smoke-user",
            channel="telegram",
            target="123",
            source_ref="smoke:outbound_fail_fallback",
            dry_run=False,
            trigger="manual",
        ),
        runtime_sender=failing_sender,
    )
    ok_outbound_fail = bool(
        not result_outbound_fail.get("ok")
        and not result_outbound_fail.get("executed")
        and str((result_outbound_fail.get("outbound_result") or {}).get("delivery_state") or "") == "failed"
    )
    emit("outbound_fail_fallback", ok_outbound_fail, result_outbound_fail)
    if not ok_outbound_fail:
        failures += 1

    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

