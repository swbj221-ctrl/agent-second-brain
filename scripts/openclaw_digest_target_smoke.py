"""OpenClaw-first outbound + digest target smoke (no aiogram polling)."""

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
from d_brain.integrations.openclaw_outbound import (  # noqa: E402
    build_openclaw_outbound,
    register_runtime_sender,
)


def emit(case: str, ok: bool, **fields: object) -> None:
    payload = {"case": case, "ok": ok}
    payload.update(fields)
    print(json.dumps(payload, ensure_ascii=True))


def fake_sidecar_action(action: str, payload: dict, user_id: str | int, source: str):
    _ = payload, user_id, source
    if action == "event_list":
        return SimpleNamespace(status="ok", data={"events": [{"title": "Plan A"}]}, error_code=None)
    if action == "task_list":
        return SimpleNamespace(status="ok", data={"tasks": [{"id": 1, "title": "Task A"}]}, error_code=None)
    return SimpleNamespace(status="ok", data={"action": action}, error_code=None)


def main() -> int:
    failures = 0
    with tempfile.TemporaryDirectory(prefix="openclaw-outbound-smoke-") as tmp:
        os.environ["HEARTBEAT_STATE_PATH"] = str(Path(tmp) / "heartbeat_state.json")
        os.environ["OPENAI_API_KEY"] = "smoke-openai-key"
        os.environ["TELEGRAM_BOT_TOKEN"] = "smoke-token"

        original_call = heartbeat_runner.call_sidecar_action
        heartbeat_runner.call_sidecar_action = fake_sidecar_action
        try:
            # case: no_target via scheduled digest path
            dispatch_command("/digest target clear", user_id=123, source_ref="111:1")
            no_target_run = dispatch_command("/cron run digest.daily", user_id=123, source_ref="111:2")
            no_target_status = dispatch_command("/digest status", user_id=123, source_ref="111:3")
            no_target_ok = bool(
                no_target_run
                and "delivery=no_target" in no_target_run
                and no_target_status
                and "delivery=no_target" in no_target_status
            )
            emit(
                "no_target",
                no_target_ok,
                cron_output=no_target_run or "",
                status_output=no_target_status or "",
            )
            if not no_target_ok:
                failures += 1

            # case: text_only with runtime sender available
            def runtime_sender(channel: str, target: str, text: str) -> dict[str, object]:
                _ = text
                return {
                    "ok": True,
                    "delivery_state": "sent",
                    "message_id": "smoke-msg-1",
                    "channel": channel,
                    "target": target,
                }

            outbound = build_openclaw_outbound(runtime_sender=runtime_sender)
            text_result = outbound.send_text(
                channel="telegram",
                target="111",
                text="smoke text",
                trigger="manual",
                provider_role="cron",
            )
            text_ok = bool(text_result.ok and text_result.delivery_state == "sent")
            emit("text_only", text_ok, result=text_result.to_dict())
            if not text_ok:
                failures += 1

            # case: runtime sender registered -> bridge cron delivery is sent
            register_runtime_sender(runtime_sender)
            try:
                dispatch_command("/digest target here", user_id=123, source_ref="111:8")
                runtime_run = dispatch_command("/cron run digest.daily", user_id=123, source_ref="111:9")
                runtime_status = dispatch_command("/digest status", user_id=123, source_ref="111:10")
                runtime_ok = bool(
                    runtime_run
                    and "delivery=sent" in runtime_run
                    and runtime_status
                    and "delivery=sent" in runtime_status
                )
                emit(
                    "runtime_sent",
                    runtime_ok,
                    cron_output=runtime_run or "",
                    status_output=runtime_status or "",
                )
                if not runtime_ok:
                    failures += 1
            finally:
                register_runtime_sender(None)

            # case: tts requested but empty -> text fallback
            tts_result = outbound.send_tts(
                channel="telegram",
                target="111",
                audio_bytes=b"",
                fallback_text="fallback text",
                trigger="manual",
                provider_role="voice_chat",
            )
            tts_ok = bool(
                tts_result.ok
                and tts_result.delivery_state == "sent"
                and tts_result.fallback_used
                and tts_result.fallback_reason == "tts_empty_output"
            )
            emit("tts_requested_but_empty", tts_ok, result=tts_result.to_dict())
            if not tts_ok:
                failures += 1
        finally:
            heartbeat_runner.call_sidecar_action = original_call

    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
