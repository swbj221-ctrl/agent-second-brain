"""Deterministic smoke checks for embedded media redirect shim (wrapper-first)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import openclaw_embedded_media_redirect_cli as redirect  # type: ignore


def _print(case: str, ok: bool, **extra: object) -> int:
    payload = {"case": case, "ok": bool(ok)}
    payload.update(extra)
    print(json.dumps(payload, ensure_ascii=True))
    return 0 if ok else 1


def main() -> int:
    failures = 0

    audio_doc = (
        "[media attached: C:\\Users\\User\\.openclaw\\media\\inbound\\file_1.ogg (audio/ogg; codecs=opus) | "
        "C:\\Users\\User\\.openclaw\\media\\inbound\\file_1.ogg]\n<media:audio> Transcript: Privet"
    )
    non_audio_doc = (
        "[media attached: C:\\Users\\User\\.openclaw\\media\\inbound\\file_2.pdf (application/pdf) | "
        "C:\\Users\\User\\.openclaw\\media\\inbound\\file_2.pdf]\n<media:file>"
    )

    original_invoke = redirect._invoke_wrapper_cli
    calls: list[dict[str, str]] = []
    try:
        def _fake_invoke(raw_text: str, request_id: str = "") -> dict[str, object]:
            calls.append({"raw_text": raw_text, "request_id": request_id})
            return {
                "returncode": 0,
                "stdout": '{"ok":true,"proof":{"event":"openclaw_voice_dispatch_path_select","selectedPath":"d_brain_openclaw_bridge"}}',
                "stderr": "",
                "json": {
                    "ok": True,
                    "proof": {
                        "event": "openclaw_voice_dispatch_path_select",
                        "selectedPath": "d_brain_openclaw_bridge",
                        "messageKind": "document",
                        "isAudioDocument": True,
                    },
                    "error_code": "",
                    "adapter_response": {"bridge_handled": True},
                    "trace": {"traceStage": "wrapper.adapter_dispatch", "requestId": request_id},
                    "user_safe_text": "ok",
                },
                "cmd": [sys.executable, "scripts/openclaw_live_voice_bridge_cli.py", "--message-text", "<omitted>"],
            }

        redirect._invoke_wrapper_cli = _fake_invoke  # type: ignore[assignment]
        result_audio = redirect.redirect_embedded_prompt(audio_doc, request_id="smoke-audio")
    finally:
        redirect._invoke_wrapper_cli = original_invoke  # type: ignore[assignment]

    failures += _print(
        "audio_invokes_wrapper_cli_with_proof_marker",
        bool(result_audio.get("wrapper_invoked"))
        and (result_audio.get("proof_marker") or {}).get("selectedPath") == "wrapper_cli_bridge"
        and (result_audio.get("proof_marker") or {}).get("traceStage") == "redirect.path_select"
        and (result_audio.get("proof_marker") or {}).get("requestId") == "smoke-audio"
        and (result_audio.get("wrapper_result") or {}).get("wrapper_proof", {}).get("selectedPath") == "d_brain_openclaw_bridge"
        and (result_audio.get("wrapper_result") or {}).get("trace", {}).get("traceStage") == "wrapper.adapter_dispatch"
        and len(calls) == 1,
        selected_path=(result_audio.get("proof_marker") or {}).get("selectedPath"),
        wrapper_selected=((result_audio.get("wrapper_result") or {}).get("wrapper_proof") or {}).get("selectedPath"),
        wrapper_trace=((result_audio.get("wrapper_result") or {}).get("trace") or {}).get("traceStage"),
        calls=len(calls),
    )

    calls.clear()
    result_non_audio = redirect.redirect_embedded_prompt(non_audio_doc, request_id="smoke-non-audio")
    failures += _print(
        "non_audio_doc_does_not_invoke_wrapper",
        (not result_non_audio.get("wrapper_invoked"))
        and result_non_audio.get("error_code") == "non_audio_media"
        and (result_non_audio.get("proof_marker") or {}).get("selectedPath") == "embedded_default_flow"
        and (result_non_audio.get("proof_marker") or {}).get("traceStage") == "redirect.path_skip"
        and len(calls) == 0,
        error_code=result_non_audio.get("error_code"),
        selected_path=(result_non_audio.get("proof_marker") or {}).get("selectedPath"),
        calls=len(calls),
    )

    original_invoke = redirect._invoke_wrapper_cli
    try:
        def _missing_wrapper(_: str, request_id: str = "") -> dict[str, object]:
            raise FileNotFoundError("missing wrapper")

        redirect._invoke_wrapper_cli = _missing_wrapper  # type: ignore[assignment]
        result_missing = redirect.redirect_embedded_prompt(audio_doc, request_id="smoke-missing")
    finally:
        redirect._invoke_wrapper_cli = original_invoke  # type: ignore[assignment]

    failures += _print(
        "wrapper_unavailable_emits_anti_silent_bypass_error_marker",
        (not result_missing.get("ok"))
        and result_missing.get("error_code") == "wrapper_cli_unavailable"
        and (result_missing.get("error_marker") or {}).get("event") == "openclaw_voice_dispatch_path_error"
        and (result_missing.get("error_marker") or {}).get("selectedPath") == "none"
        and (result_missing.get("error_marker") or {}).get("intendedPath") == "wrapper_cli_bridge",
        error_code=result_missing.get("error_code"),
        error_marker=result_missing.get("error_marker"),
    )

    original_invoke = redirect._invoke_wrapper_cli
    try:
        def _unexpected_non_bridge(_raw_text: str, request_id: str = "") -> dict[str, object]:
            return {
                "returncode": 0,
                "stdout": "{}",
                "stderr": "",
                "json": {
                    "ok": True,
                    "proof": {
                        "event": "openclaw_voice_dispatch_path_select",
                        "selectedPath": "embedded_direct_stt",
                        "traceStage": "wrapper.path_select",
                        "requestId": request_id,
                    },
                    "trace": {"traceStage": "wrapper.path_skip", "requestId": request_id},
                },
                "cmd": [sys.executable, "scripts/openclaw_live_voice_bridge_cli.py", "--message-text", "<omitted>"],
            }

        redirect._invoke_wrapper_cli = _unexpected_non_bridge  # type: ignore[assignment]
        result_unexpected = redirect.redirect_embedded_prompt(audio_doc, request_id="smoke-unexpected")
    finally:
        redirect._invoke_wrapper_cli = original_invoke  # type: ignore[assignment]

    failures += _print(
        "audio_wrapper_non_bridge_path_is_blocked",
        (not result_unexpected.get("ok"))
        and result_unexpected.get("error_code") == "wrapper_unexpected_non_bridge_path"
        and (result_unexpected.get("error_marker") or {}).get("errorCode") == "wrapper_unexpected_non_bridge_path",
        error_code=result_unexpected.get("error_code"),
        error_marker=result_unexpected.get("error_marker"),
    )

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
