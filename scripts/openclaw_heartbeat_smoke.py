"""Deterministic smoke test for OpenClaw heartbeat runner (no aiogram)."""

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


def emit(case: str, ok: bool, **fields: object) -> None:
    payload = {"case": case, "ok": ok}
    payload.update(fields)
    print(json.dumps(payload, ensure_ascii=True))


def fake_sidecar_action(action: str, payload: dict, user_id: str | int, source: str):
    _ = payload, user_id, source
    return SimpleNamespace(status="ok", data={"action": action}, error_code=None, error_message=None)


def main() -> int:
    failures = 0
    with tempfile.TemporaryDirectory(prefix="openclaw-heartbeat-smoke-") as tmp:
        os.environ["HEARTBEAT_STATE_PATH"] = str(Path(tmp) / "heartbeat_state.json")
        os.environ["OPENAI_API_KEY"] = "smoke-openai-key"
        os.environ["MODEL_ROUTE_HEARTBEAT_PROVIDER"] = "local"
        os.environ["MODEL_ROUTE_ALLOW_LOCAL_TO_OPENAI_FALLBACK"] = "true"
        os.environ["MODEL_ROUTE_FORCE_LOCAL_UNAVAILABLE"] = "false"

        original_call = heartbeat_runner.call_sidecar_action
        heartbeat_runner.call_sidecar_action = fake_sidecar_action
        try:
            success = heartbeat_runner.run_heartbeat_tick_sync()
            success_ok = (
                bool(success.get("ok"))
                and success.get("status") == "ok"
                and success.get("provider") == "local"
                and bool(success.get("actions"))
            )
            emit(
                "heartbeat_tick_success",
                success_ok,
                status=success.get("status"),
                provider=success.get("provider"),
                fallback_used=bool(success.get("fallback_used")),
                actions=len(success.get("actions") or []),
            )
            if not success_ok:
                failures += 1

            os.environ["MODEL_ROUTE_FORCE_LOCAL_UNAVAILABLE"] = "true"
            fallback = heartbeat_runner.run_heartbeat_tick_sync()
            fallback_ok = (
                bool(fallback.get("ok"))
                and fallback.get("provider") == "openai"
                and bool(fallback.get("fallback_used"))
            )
            emit(
                "heartbeat_local_unavailable_fallback",
                fallback_ok,
                status=fallback.get("status"),
                provider=fallback.get("provider"),
                fallback_used=bool(fallback.get("fallback_used")),
                reason=fallback.get("reason") or "",
            )
            if not fallback_ok:
                failures += 1

            state = heartbeat_runner.get_heartbeat_status()
            state_ok = bool(state.get("last_run_at")) and bool(state.get("last_provider"))
            emit(
                "heartbeat_state_written",
                state_ok,
                last_status=state.get("last_status"),
                last_provider=state.get("last_provider"),
            )
            if not state_ok:
                failures += 1
        finally:
            heartbeat_runner.call_sidecar_action = original_call

    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
