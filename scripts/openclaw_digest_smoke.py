"""Digest runner smoke for OpenClaw bridge (no aiogram polling)."""

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


def emit(case: str, command: str, output: str | None, ok: bool) -> None:
    print(json.dumps({"case": case, "command": command, "ok": ok, "output": output or ""}, ensure_ascii=True))


def fake_sidecar_action(action: str, payload: dict, user_id: str | int, source: str):
    _ = user_id, source
    if action == "event_list":
        return SimpleNamespace(status="ok", data={"events": [{"title": "РџР»Р°РЅ 1"}, {"title": "РџР»Р°РЅ 2"}]}, error_code=None)
    if action == "task_list":
        return SimpleNamespace(status="ok", data={"tasks": [{"id": 1, "title": "Р—Р°РґР°С‡Р° 1"}]}, error_code=None)
    return SimpleNamespace(status="ok", data={"action": action, "payload": payload}, error_code=None)


def main() -> int:
    failures = 0
    with tempfile.TemporaryDirectory(prefix="openclaw-digest-smoke-") as tmp:
        os.environ["HEARTBEAT_STATE_PATH"] = str(Path(tmp) / "heartbeat_state.json")
        os.environ["OPENAI_API_KEY"] = "smoke-openai-key"
        os.environ["MODEL_ROUTE_CRON_SUMMARY_PROVIDER"] = "local"

        original_call = heartbeat_runner.call_sidecar_action
        heartbeat_runner.call_sidecar_action = fake_sidecar_action
        try:
            steps = [
                ("digest_preview", "/digest preview", lambda out: bool(out and len(out) > 80 and "heartbeat" in out)),
                ("digest_now", "/digest now", lambda out: bool(out and len(out) > 80 and "heartbeat" in out)),
                ("digest_status_1", "/digest status", lambda out: bool(out and "last_status=ok" in out)),
                (
                    "cron_run_digest",
                    "/cron run digest.daily",
                    lambda out: bool(out and "job=digest.daily" in out),
                ),
                ("digest_status_2", "/digest status", lambda out: bool(out and "source=" in out)),
            ]

            for case, command, check in steps:
                output = dispatch_command(command, user_id=123, source_ref=f"smoke:{case}")
                ok = check(output)
                emit(case, command, output, ok)
                if not ok:
                    failures += 1
        finally:
            heartbeat_runner.call_sidecar_action = original_call

    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
