"""Targeted smoke test for top-level chat_response_source enforcement."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from importlib import util


ADAPTER_PATH = ROOT / "vault" / ".claude" / "skills" / "openclaw-main" / "adapter.py"
spec = util.spec_from_file_location("openclaw_adapter_smoke", ADAPTER_PATH)
if spec is None or spec.loader is None:
    raise SystemExit("adapter_load_failed")
adapter = util.module_from_spec(spec)
sys.modules["openclaw_adapter_smoke"] = adapter
spec.loader.exec_module(adapter)


def _run_case(name: str, fake_response: dict, expected_source: str, expect_fail_closed: bool) -> int:
    original = adapter.dispatch_voice_from_message
    try:
        adapter.dispatch_voice_from_message = lambda message, user_id, request_id=None: fake_response
        result = adapter.main_handler_response(
            {
                "chat_id": 5124291327,
                "message_id": 1,
                "user_id": 5124291327,
                "audio_path": "C:/tmp/demo.ogg",
                "audio": {"mime_type": "audio/ogg"},
                "text": "Transcript: provider text",
                "request_id": f"smoke-{name}",
            }
        )
        diagnostics = result.get("diagnostics") or {}
        source = str(diagnostics.get("chat_response_source") or "")
        fail_closed = "Voice processing is temporarily unavailable" in str(result.get("text") or "")
        ok = source == expected_source and (fail_closed == expect_fail_closed)
        print(f"case={name}")
        print(f"ok={ok}")
        print(f"chat_response_source={source}")
        print(f"media_or_inferred={bool(diagnostics.get('media_or_inferred'))}")
        if not ok:
            print(f"text={result.get('text')}")
            return 1
        return 0
    finally:
        adapter.dispatch_voice_from_message = original


def main() -> int:
    failures = 0
    failures += _run_case(
        "provider_transcript_blocked",
        {
            "handled": True,
            "status": "ok",
            "text": "how are you",
            "diagnostics": {"final_transcript_source_used": "provider_transcript"},
        },
        expected_source="provider_transcript_blocked",
        expect_fail_closed=True,
    )
    failures += _run_case(
        "bridge_stt_pass",
        {
            "handled": True,
            "status": "ok",
            "text": "привет",
            "diagnostics": {"final_transcript_source_used": "bridge_stt"},
        },
        expected_source="bridge_stt",
        expect_fail_closed=False,
    )
    failures += _run_case(
        "fallback_error",
        {
            "handled": True,
            "status": "error",
            "text": "",
            "diagnostics": {"fallback_reason": "stt_empty"},
        },
        expected_source="fallback_error",
        expect_fail_closed=True,
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
