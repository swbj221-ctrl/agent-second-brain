"""Deterministic smoke checks for the OpenClaw embedded voice bridge wrapper."""

from __future__ import annotations

import json
import base64
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

sys.path.insert(0, str(ROOT / "scripts"))
import openclaw_live_voice_bridge_cli as wrapper  # type: ignore


def _print(case: str, ok: bool, **extra: object) -> int:
    payload = {"case": case, "ok": bool(ok)}
    payload.update(extra)
    print(json.dumps(payload, ensure_ascii=True))
    return 0 if ok else 1


def main() -> int:
    failures = 0

    ru_text = "Привет мир"
    ru_b64 = base64.b64encode(ru_text.encode("utf-8")).decode("ascii")
    ru_b64_prompt = (
        "[Audio] User text: [Telegram Hv (@hvhvhv12) id:5124291327 Wed 2026-02-25 01:59 GMT+3] "
        f"<media:audio> TranscriptB64: {ru_b64}"
    )
    parsed_ru_b64 = wrapper.parse_openclaw_embedded_media_prompt(ru_b64_prompt)
    failures += _print(
        "transcript_b64_ru_decodes_utf8",
        parsed_ru_b64.get("transcript") == ru_text
        and parsed_ru_b64.get("transcript_status") == "OK"
        and parsed_ru_b64.get("transcript_decode_mode") == "base64_utf8"
        and parsed_ru_b64.get("transcript_base64_decoded") is True,
        transcript=parsed_ru_b64.get("transcript"),
        transcript_status=parsed_ru_b64.get("transcript_status"),
        decode_mode=parsed_ru_b64.get("transcript_decode_mode"),
    )

    mixed = (
        "[Audio] User text: [Telegram Hv (@hvhvhv12) id:5124291327 Wed 2026-02-25 01:59 GMT+3] "
        "<media:audio> Transcript: Привет hello one two три"
    )
    parsed_mixed = wrapper.parse_openclaw_embedded_media_prompt(mixed)
    failures += _print(
        "audio_user_text_routes_to_bridge",
        parsed_mixed["selected_path"] == "d_brain_openclaw_bridge"
        and parsed_mixed.get("transcript_status") == "OK"
        and parsed_mixed.get("transcript_decode_mode") == "raw_utf8",
        selected_path=parsed_mixed["selected_path"],
        message_kind=parsed_mixed["media_kind"],
        user_id=parsed_mixed["user_id"],
        transcript_status=parsed_mixed.get("transcript_status"),
        decode_mode=parsed_mixed.get("transcript_decode_mode"),
    )

    empty_prompt = (
        "[Audio] User text: [Telegram Hv (@hvhvhv12) id:5124291327 Wed 2026-02-25 01:59 GMT+3] "
        "<media:audio> Transcript:   "
    )
    parsed_empty = wrapper.parse_openclaw_embedded_media_prompt(empty_prompt)
    failures += _print(
        "empty_transcript_is_explicit_status",
        parsed_empty.get("transcript_status") == "EMPTY_TRANSCRIPT" and parsed_empty.get("transcript") == "",
        transcript_status=parsed_empty.get("transcript_status"),
        transcript=parsed_empty.get("transcript"),
    )

    mojibake_prompt = (
        "[Audio] User text: [Telegram Hv (@hvhvhv12) id:5124291327 Wed 2026-02-25 01:59 GMT+3] "
        "<media:audio> Transcript: РџСЂРёРІРµС‚ РјРёСЂ"
    )
    parsed_mojibake = wrapper.parse_openclaw_embedded_media_prompt(mojibake_prompt)
    failures += _print(
        "mojibake_transcript_detected",
        parsed_mojibake.get("transcript_mojibake_suspected") is True and parsed_mojibake.get("transcript_status") == "OK",
        transcript_preview=str(parsed_mojibake.get("transcript"))[:40],
        transcript_status=parsed_mojibake.get("transcript_status"),
        mojibake=parsed_mojibake.get("transcript_mojibake_suspected"),
    )

    audio_doc = (
        "[media attached: C:\\Users\\User\\.openclaw\\media\\inbound\\file_1.ogg (audio/ogg; codecs=opus) | "
        "C:\\Users\\User\\.openclaw\\media\\inbound\\file_1.ogg]\n<media:audio>"
    )
    parsed_audio_doc = wrapper.parse_openclaw_embedded_media_prompt(audio_doc)
    failures += _print(
        "audio_document_routes_to_bridge",
        parsed_audio_doc["selected_path"] == "d_brain_openclaw_bridge",
        selected_path=parsed_audio_doc["selected_path"],
        mime_type=parsed_audio_doc["mime_type"],
        ext=parsed_audio_doc["ext"],
        message_kind=parsed_audio_doc["media_kind"],
    )

    non_audio_doc = (
        "[media attached: C:\\Users\\User\\.openclaw\\media\\inbound\\file_2.pdf (application/pdf) | "
        "C:\\Users\\User\\.openclaw\\media\\inbound\\file_2.pdf]\n<media:file>"
    )
    parsed_non_audio = wrapper.parse_openclaw_embedded_media_prompt(non_audio_doc)
    failures += _print(
        "non_audio_document_not_routed_to_voice_bridge",
        parsed_non_audio["selected_path"] != "d_brain_openclaw_bridge",
        selected_path=parsed_non_audio["selected_path"],
        mime_type=parsed_non_audio["mime_type"],
        ext=parsed_non_audio["ext"],
    )

    # Ensure explicit non-audio result emits proof marker and no silent bridge call.
    result_non_audio = wrapper.route_embedded_media_prompt_via_bridge(non_audio_doc, request_id="smoke-non-audio")
    failures += _print(
        "non_audio_wrapper_returns_diagnostic_skip",
        (not result_non_audio.get("ok"))
        and (result_non_audio.get("proof") or {}).get("selectedPath") == "embedded_direct_stt"
        and (result_non_audio.get("proof") or {}).get("messageKind") == "document"
        and (result_non_audio.get("proof") or {}).get("isAudioDocument") is False
        and result_non_audio.get("error_code") == "non_audio_media",
        selected_path=(result_non_audio.get("proof") or {}).get("selectedPath"),
        message_kind=(result_non_audio.get("proof") or {}).get("messageKind"),
        is_audio_document=(result_non_audio.get("proof") or {}).get("isAudioDocument"),
        error_code=result_non_audio.get("error_code"),
    )

    # Observable proof fields in wrapper JSON result for audio document branch (deterministic fake adapter).
    original_loader = wrapper._load_adapter_module
    try:
        class _ObsFakeAdapterMod:
            @staticmethod
            def main_handler_response(msg: dict[str, object]) -> dict[str, object]:
                return {"status": "ok", "text": "ok", "bridge_handled": True, "diagnostics": {}}

        def _obs_fake_loader() -> object:
            return _ObsFakeAdapterMod()

        wrapper._load_adapter_module = _obs_fake_loader  # type: ignore[assignment]
        result_audio_doc = wrapper.route_embedded_media_prompt_via_bridge(audio_doc, request_id="smoke-audio-doc")
    finally:
        wrapper._load_adapter_module = original_loader  # type: ignore[assignment]

    failures += _print(
        "audio_document_result_includes_observable_proof",
        (result_audio_doc.get("proof") or {}).get("selectedPath") == "d_brain_openclaw_bridge"
        and (result_audio_doc.get("proof") or {}).get("messageKind") == "document"
        and (result_audio_doc.get("proof") or {}).get("isAudioDocument") is True
        and "embedded_transcript_status" in (((result_audio_doc.get("adapter_response") or {}).get("diagnostics")) or {}),
        ok_result=result_audio_doc.get("ok"),
        selected_path=(result_audio_doc.get("proof") or {}).get("selectedPath"),
        message_kind=(result_audio_doc.get("proof") or {}).get("messageKind"),
        is_audio_document=(result_audio_doc.get("proof") or {}).get("isAudioDocument"),
        error_code=result_audio_doc.get("error_code"),
    )

    original_loader = wrapper._load_adapter_module
    try:
        captured_msg: dict[str, object] = {}

        class _FakeAdapterMod:
            @staticmethod
            def main_handler_response(msg: dict[str, object]) -> dict[str, object]:
                captured_msg.clear()
                captured_msg.update(msg)
                return {"status": "ok", "text": "ok", "bridge_handled": True, "diagnostics": {}}

        def _fake_loader() -> object:
            return _FakeAdapterMod()

        wrapper._load_adapter_module = _fake_loader  # type: ignore[assignment]
        mojibake_audio_doc = (
            "[media attached: C:\\Users\\User\\.openclaw\\media\\inbound\\file_3.ogg (audio/ogg; codecs=opus) | "
            "C:\\Users\\User\\.openclaw\\media\\inbound\\file_3.ogg]\n"
            "<media:audio>\nTranscript: РџСЂРёРІРµС‚"
        )
        result_mojibake_route = wrapper.route_embedded_media_prompt_via_bridge(
            mojibake_audio_doc,
            request_id="smoke-mojibake-route",
        )
    finally:
        wrapper._load_adapter_module = original_loader  # type: ignore[assignment]

    failures += _print(
        "mojibake_transcript_not_forwarded_as_text",
        bool(result_mojibake_route.get("ok"))
        and captured_msg.get("text") == ""
        and (((result_mojibake_route.get("adapter_response") or {}).get("diagnostics")) or {}).get(
            "embedded_transcript_mojibake_suspected"
        )
        is True,
        forwarded_text=captured_msg.get("text"),
        diagnostics=(result_mojibake_route.get("adapter_response") or {}).get("diagnostics"),
    )

    try:
        def _raise_loader() -> object:
            raise RuntimeError("smoke_bridge_fail")

        wrapper._load_adapter_module = _raise_loader  # type: ignore[assignment]
        result_bridge_fail = wrapper.route_embedded_media_prompt_via_bridge(audio_doc, request_id="smoke-bridge-fail")
    finally:
        wrapper._load_adapter_module = original_loader  # type: ignore[assignment]

    failures += _print(
        "audio_bridge_failure_emits_anti_silent_bypass_marker",
        (not result_bridge_fail.get("ok"))
        and result_bridge_fail.get("error_code") == "bridge_dispatch_unavailable"
        and (result_bridge_fail.get("error_marker") or {}).get("event") == "openclaw_voice_dispatch_path_error"
        and (result_bridge_fail.get("error_marker") or {}).get("selectedPath") == "none"
        and (result_bridge_fail.get("error_marker") or {}).get("intendedPath") == "d_brain_openclaw_bridge",
        error_code=result_bridge_fail.get("error_code"),
        marker=result_bridge_fail.get("error_marker"),
    )

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
