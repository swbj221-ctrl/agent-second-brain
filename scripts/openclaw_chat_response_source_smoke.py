"""Focused smoke for final outgoing text source enforcement on media turns."""

from __future__ import annotations

import sys
from importlib import util
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

ADAPTER_PATH = ROOT / "vault" / ".claude" / "skills" / "openclaw-main" / "adapter.py"
SPEC = util.spec_from_file_location("openclaw_adapter_smoke", ADAPTER_PATH)
if SPEC is None or SPEC.loader is None:
    raise SystemExit("adapter_load_failed")
adapter = util.module_from_spec(SPEC)
sys.modules["openclaw_adapter_smoke"] = adapter
SPEC.loader.exec_module(adapter)


def _build_live_like_message(case_name: str) -> dict[str, Any]:
    return {
        "chat_id": 5124291327,
        "message_id": 1,
        "user_id": 5124291327,
        "request_id": f"smoke-{case_name}",
        "runId": f"run-{case_name}",
        "sessionId": f"session-{case_name}",
        "audio_path": "C:/tmp/demo.ogg",
        "audio": {"mime_type": "audio/ogg"},
        "content": "[media attached: demo.ogg]\n<media:audio>\nTranscript: how are you",
        "text": "Transcript: how are you",
    }


def _run_case(
    *,
    name: str,
    fake_response: dict[str, Any],
    expected_source: str,
    expected_text_contains: str | None = None,
    expect_fail_closed: bool = False,
) -> int:
    original = adapter.dispatch_voice_from_message
    try:
        adapter.dispatch_voice_from_message = lambda message, user_id, request_id=None: fake_response
        result = adapter.main_handler_response(_build_live_like_message(name))
    finally:
        adapter.dispatch_voice_from_message = original

    diagnostics = result.get("diagnostics") or {}
    chat_source = str(diagnostics.get("chat_response_source") or "")
    outgoing_source = str(diagnostics.get("outgoing_text_source") or "")
    media_or_inferred = bool(diagnostics.get("media_or_inferred"))
    text = str(result.get("text") or "")
    fail_closed = "Voice processing is temporarily unavailable" in text
    text_ok = True if expected_text_contains is None else expected_text_contains in text
    ok = (
        chat_source == expected_source
        and outgoing_source == expected_source
        and media_or_inferred is True
        and fail_closed == expect_fail_closed
        and text_ok
    )
    print(f"case={name}")
    print(f"ok={ok}")
    print(f"chat_response_source={chat_source}")
    print(f"outgoing_text_source={outgoing_source}")
    print(f"media_or_inferred={media_or_inferred}")
    print(f"text={text}")
    if not ok:
        return 1
    return 0


def main() -> int:
    failures = 0

    failures += _run_case(
        name="provider_transcript_blocked",
        fake_response={
            "handled": True,
            "status": "ok",
            "text": "how are you",
            "diagnostics": {"final_transcript_source_used": "provider_transcript"},
        },
        expected_source="provider_transcript_blocked",
        expect_fail_closed=True,
    )

    failures += _run_case(
        name="fallback_error",
        fake_response={
            "handled": True,
            "status": "error",
            "text": "",
            "diagnostics": {"fallback_reason": "stt_empty"},
        },
        expected_source="fallback_error",
        expect_fail_closed=True,
    )

    mixed_full = "\u041f\u0440\u0438\u0432\u0435\u0442 how are you \u0442\u044b \u043c\u0435\u043d\u044f \u043f\u043e\u043d\u0438\u043c\u0430\u0435\u0448\u044c?"
    failures += _run_case(
        name="embedded_preflight_tail_bridge_full_sequence",
        fake_response={
            "handled": True,
            "status": "ok",
            "text": "how are you",
            "diagnostics": {
                "mode": "default",
                "final_transcript_source_used": "bridge_stt",
                "bridge_candidate_text": mixed_full,
                "stt_multipass_selected_transcript": mixed_full,
            },
        },
        expected_source="bridge_stt",
        expected_text_contains=mixed_full,
        expect_fail_closed=False,
    )

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
