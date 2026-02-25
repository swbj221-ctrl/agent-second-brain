"""Bridge wrapper for OpenClaw embedded Telegram audio/voice messages.

Purpose:
- Detect OpenClaw-formatted embedded media prompts (`<media:audio>` and media metadata)
- Route audio/voice/audio-document payloads into the existing OpenClaw adapter -> d_brain bridge path
- Emit proof-level structured JSON for path selection (no secrets)

This is a narrow compatibility wrapper for live OpenClaw embedded agent flows.
"""

from __future__ import annotations

import argparse
import base64
import importlib.util
import json
import os
import re
import sys
from pathlib import Path
from typing import Any


_MEDIA_ATTACHED_RE = re.compile(
    r"\[media attached:\s*(?P<path>.+?)\s+\((?P<meta>[^)]*)\)\s+\|\s*(?P=path)\]",
    re.IGNORECASE | re.DOTALL,
)
_AUDIO_USER_TEXT_RE = re.compile(r"^\[Audio\]\s+User text:\s*(?P<body>.*)$", re.IGNORECASE | re.DOTALL)
_TRANSCRIPT_RE = re.compile(r"\bTranscript:\s*(?P<transcript>.+)$", re.IGNORECASE | re.DOTALL)
_TRANSCRIPT_B64_RE = re.compile(
    r"\bTranscript(?:B64|Base64):\s*(?P<transcript_b64>[A-Za-z0-9+/=\r\n]+)$",
    re.IGNORECASE | re.DOTALL,
)
_TELEGRAM_ID_RE = re.compile(r"\bid:(?P<id>\d+)\b")


def _safe_preview(text: str, max_len: int = 180) -> str:
    value = " ".join((text or "").split())
    return value if len(value) <= max_len else value[:max_len] + "...<trimmed>"


def _configure_utf8_stdio() -> None:
    # Keep wrapper JSON output deterministic across Windows shells/exec wrappers.
    for stream_name in ("stdin", "stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def _looks_like_mojibake(text: str) -> bool:
    value = str(text or "")
    if not value:
        return False
    lowered = value.lower()
    if "\u043f\u0457" in lowered or "\ufffd" in value:
        return True
    if "???" in value and re.search(r"[\u0420\u0421]", value):
        return True
    # Classic UTF-8->ANSI mojibake often forms repeated Cyrillic "?x"/"?x" digraphs.
    if len(re.findall(r"[\u0420\u0421][^\s]", value)) >= 4:
        return True
    return False


def _extract_transcript_payload(text: str) -> dict[str, Any]:
    raw = str(text or "")
    b64_match = _TRANSCRIPT_B64_RE.search(raw)
    if b64_match:
        encoded = "".join(str(b64_match.group("transcript_b64") or "").split())
        if not encoded:
            return {
                "text": "",
                "status": "EMPTY_TRANSCRIPT",
                "decode_mode": "base64_utf8",
                "base64_decoded": True,
                "mojibake_suspected": False,
            }
        try:
            decoded = base64.b64decode(encoded, validate=True).decode("utf-8")
            transcript = decoded.strip()
            return {
                "text": transcript,
                "status": "OK" if transcript else "EMPTY_TRANSCRIPT",
                "decode_mode": "base64_utf8",
                "base64_decoded": True,
                "mojibake_suspected": _looks_like_mojibake(transcript),
            }
        except Exception:
            return {
                "text": "",
                "status": "EMPTY_TRANSCRIPT",
                "decode_mode": "base64_invalid",
                "base64_decoded": False,
                "mojibake_suspected": False,
            }

    tr = _TRANSCRIPT_RE.search(raw)
    transcript = str(tr.group("transcript") or "").strip() if tr else ""
    mojibake = _looks_like_mojibake(transcript)
    return {
        "text": transcript,
        "status": "OK" if transcript else "EMPTY_TRANSCRIPT",
        "decode_mode": "raw_utf8",
        "base64_decoded": False,
        "mojibake_suspected": mojibake,
    }


def _is_audio_mime_or_name(mime_type: str, path_text: str) -> bool:
    mime = (mime_type or "").strip().lower()
    if mime.startswith("audio/"):
        return True
    suffix = Path(path_text or "").suffix.lower()
    return suffix in {".ogg", ".opus", ".m4a", ".mp3", ".wav", ".mpeg"}


def parse_openclaw_embedded_media_prompt(raw_text: str) -> dict[str, Any]:
    text = str(raw_text or "")
    media_tag_audio = "<media:audio>" in text.lower()
    media_tag_file = "<media:file>" in text.lower()
    audio_user_text = bool(_AUDIO_USER_TEXT_RE.search(text))

    path_text = ""
    mime_type = ""
    ext = ""
    transcript = ""
    transcript_status = "EMPTY_TRANSCRIPT"
    transcript_decode_mode = "none"
    transcript_base64_decoded = False
    transcript_mojibake_suspected = False
    media_kind = ""
    source_format = ""

    attached_match = _MEDIA_ATTACHED_RE.search(text)
    if attached_match:
        path_text = str(attached_match.group("path") or "").strip()
        meta = str(attached_match.group("meta") or "")
        mime_match = re.search(r"([A-Za-z0-9.+-]+/[A-Za-z0-9.+-]+)", meta)
        mime_type = str(mime_match.group(1) if mime_match else "").lower()
        ext = Path(path_text).suffix.lower()
        source_format = "media_attached"
        media_kind = "document"

    audio_text_match = _AUDIO_USER_TEXT_RE.search(text)
    if audio_text_match:
        body = str(audio_text_match.group("body") or "")
        transcript_info = _extract_transcript_payload(body)
        transcript = str(transcript_info.get("text") or "")
        transcript_status = str(transcript_info.get("status") or "EMPTY_TRANSCRIPT")
        transcript_decode_mode = str(transcript_info.get("decode_mode") or "raw_utf8")
        transcript_base64_decoded = bool(transcript_info.get("base64_decoded"))
        transcript_mojibake_suspected = bool(transcript_info.get("mojibake_suspected"))
        source_format = source_format or "audio_user_text"
        media_kind = media_kind or "audio"

    if not transcript:
        transcript_info = _extract_transcript_payload(text)
        transcript = str(transcript_info.get("text") or "")
        transcript_status = str(transcript_info.get("status") or "EMPTY_TRANSCRIPT")
        transcript_decode_mode = str(transcript_info.get("decode_mode") or "raw_utf8")
        transcript_base64_decoded = bool(transcript_info.get("base64_decoded"))
        transcript_mojibake_suspected = bool(transcript_info.get("mojibake_suspected"))

    user_id = 0
    chat_id = 0
    id_match = _TELEGRAM_ID_RE.search(text)
    if id_match:
        try:
            user_id = int(id_match.group("id"))
            chat_id = user_id
        except Exception:
            user_id = 0
            chat_id = 0

    if media_tag_audio and not media_kind:
        media_kind = "audio"
    if media_tag_file and not media_kind:
        media_kind = "document"

    is_audio_payload = bool(media_tag_audio) or _is_audio_mime_or_name(mime_type, path_text)
    is_audio_document = bool(media_kind == "document" and _is_audio_mime_or_name(mime_type, path_text))
    selected_path = "d_brain_openclaw_bridge" if is_audio_payload else "embedded_direct_stt"
    branch_reason = (
        "audio_media_detected" if is_audio_payload else "non_audio_or_unrecognized_media"
    )

    return {
        "selected_path": selected_path,
        "branch_reason": branch_reason,
        "source_format": source_format,
        "media_kind": media_kind or ("audio" if is_audio_payload else "unknown"),
        "mime_type": mime_type,
        "ext": ext,
        "audio_path": path_text,
        "transcript": transcript,
        "transcript_status": transcript_status,
        "transcript_decode_mode": transcript_decode_mode,
        "transcript_base64_decoded": transcript_base64_decoded,
        "transcript_mojibake_suspected": transcript_mojibake_suspected,
        "raw_preview": _safe_preview(text),
        "user_id": user_id,
        "chat_id": chat_id,
        "is_audio_payload": is_audio_payload,
        "is_audio_document": is_audio_document,
    }


def _load_adapter_module() -> Any:
    root = Path(__file__).resolve().parents[1]
    adapter_path = root / "vault" / ".claude" / "skills" / "openclaw-main" / "adapter.py"
    module_name = "openclaw_main_adapter_live_bridge"
    spec = importlib.util.spec_from_file_location(module_name, adapter_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"adapter_load_failed:{adapter_path}")
    module = importlib.util.module_from_spec(spec)
    # Ensure dataclass/type-resolution paths can find module globals during import.
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def route_embedded_media_prompt_via_bridge(raw_text: str, *, request_id: str | None = None) -> dict[str, Any]:
    parsed = parse_openclaw_embedded_media_prompt(raw_text)
    parsed_message_kind = str(parsed.get("media_kind") or "")
    is_audio_document = bool(parsed.get("is_audio_document"))
    proof = {
        "event": "openclaw_voice_dispatch_path_select",
        "selectedPath": parsed["selected_path"],
        "branchReason": parsed["branch_reason"],
        "messageKind": parsed_message_kind,
        "isAudioDocument": is_audio_document,
        "mimeType": parsed.get("mime_type") or "",
        "ext": parsed.get("ext") or "",
        "sourceFormat": parsed.get("source_format") or "",
        "sourceModule": __file__,
    }
    if parsed["selected_path"] != "d_brain_openclaw_bridge":
        return {
            "ok": False,
            "proof": proof,
            "error_code": "non_audio_media",
            "path_fallback_reason": "non_audio_media_not_routed_to_voice_bridge",
            "user_safe_text": "",
            "adapter_response": None,
            "parsed": parsed,
        }

    audio_path = str(parsed.get("audio_path") or "").strip()
    if not audio_path:
        error_marker = {
            "event": "openclaw_voice_dispatch_path_error",
            "errorCode": "bridge_dispatch_unavailable",
            "selectedPath": "none",
            "intendedPath": "d_brain_openclaw_bridge",
            "branchReason": "audio_media_detected_but_path_missing",
            "messageKind": parsed_message_kind,
            "isAudioDocument": is_audio_document,
            "sourceModule": __file__,
        }
        return {
            "ok": False,
            "proof": proof,
            "error_marker": error_marker,
            "error_code": "bridge_dispatch_unavailable",
            "path_fallback_reason": "embedded_prompt_missing_audio_path",
            "user_safe_text": "Voice input was detected, but the media file path was not available. Please resend the voice message.",
            "adapter_response": None,
            "parsed": parsed,
        }

    try:
        # Embedded wrapper may run outside full bot runtime env; provide a safe
        # placeholder token so adapter settings can initialize for local STT path.
        if not os.getenv("TELEGRAM_BOT_TOKEN") and not os.getenv("telegram_bot_token"):
            os.environ["TELEGRAM_BOT_TOKEN"] = "embedded-wrapper-placeholder-token"
        adapter = _load_adapter_module()
        embedded_transcript_text = str(parsed.get("transcript") or "")
        embedded_transcript_mojibake = bool(parsed.get("transcript_mojibake_suspected"))
        # If shell/path encoding mangled the embedded transcript, prefer media STT only.
        if embedded_transcript_mojibake:
            embedded_transcript_text = ""
        msg: dict[str, Any] = {
            "text": embedded_transcript_text,
            "user_id": int(parsed.get("user_id") or 0),
            "from_user_id": int(parsed.get("user_id") or 0),
            "chat_id": int(parsed.get("chat_id") or 0),
            "message_id": 0,
            "request_id": request_id or "",
            "audio_path": audio_path,
            "media_path": audio_path,
            "media_declared": True,
        }
        mime_type = str(parsed.get("mime_type") or "")
        media_kind = str(parsed.get("media_kind") or "")
        if media_kind == "document":
            msg["document"] = {"mime_type": mime_type or "audio/ogg", "file_name": Path(audio_path).name}
        elif media_kind == "voice":
            msg["voice"] = {"mime_type": mime_type or "audio/ogg"}
        else:
            msg["audio"] = {"mime_type": mime_type or "audio/ogg"}
        response = adapter.main_handler_response(msg)
        return {
            "ok": True,
            "proof": proof,
            "error_code": "",
            "path_fallback_reason": "",
            "user_safe_text": str(response.get("text") or ""),
            "adapter_response": {
                "status": str(response.get("status") or ""),
                "route": str(response.get("route") or ""),
                "bridge_handled": bool(response.get("bridge_handled")),
                "audio_intent": str(response.get("audio_intent") or ""),
                "error_code": str(response.get("error_code") or ""),
                "text_preview": _safe_preview(str(response.get("text") or "")),
                "diagnostics": {
                    "stt_error_code": str((response.get("diagnostics") or {}).get("stt_error_code") or ""),
                    "pipeline_error_code": str((response.get("diagnostics") or {}).get("pipeline_error_code") or ""),
                    "stt_language": str((response.get("diagnostics") or {}).get("stt_language") or ""),
                    "stt_multipass": bool((response.get("diagnostics") or {}).get("stt_multipass")),
                    "embedded_transcript_status": str(parsed.get("transcript_status") or ""),
                    "embedded_transcript_decode_mode": str(parsed.get("transcript_decode_mode") or ""),
                    "embedded_transcript_len": len(str(parsed.get("transcript") or "")),
                    "embedded_transcript_base64_decoded": bool(parsed.get("transcript_base64_decoded")),
                    "embedded_transcript_mojibake_suspected": embedded_transcript_mojibake,
                },
            },
            "parsed": {
                "message_kind": parsed.get("media_kind"),
                "mime_type": parsed.get("mime_type"),
                "ext": parsed.get("ext"),
                "audio_path": audio_path,
                "transcript_status": parsed.get("transcript_status"),
                "transcript_decode_mode": parsed.get("transcript_decode_mode"),
                "transcript_base64_decoded": bool(parsed.get("transcript_base64_decoded")),
                "transcript_mojibake_suspected": embedded_transcript_mojibake,
                "transcript_preview": _safe_preview(str(parsed.get("transcript") or "")),
            },
        }
    except Exception as exc:
        error_marker = {
            "event": "openclaw_voice_dispatch_path_error",
            "errorCode": "bridge_dispatch_unavailable",
            "selectedPath": "none",
            "intendedPath": "d_brain_openclaw_bridge",
            "branchReason": "bridge_import_or_runtime_failed",
            "messageKind": parsed_message_kind,
            "isAudioDocument": is_audio_document,
            "sourceModule": __file__,
        }
        return {
            "ok": False,
            "proof": proof,
            "error_marker": error_marker,
            "error_code": "bridge_dispatch_unavailable",
            "path_fallback_reason": "bridge_import_or_runtime_failed",
            "user_safe_text": "Voice processing is temporarily unavailable. Please try again in a minute.",
            "adapter_response": None,
            "parsed": parsed,
            "error_detail": f"{type(exc).__name__}:{str(exc)[:160]}",
        }


def main() -> int:
    _configure_utf8_stdio()
    parser = argparse.ArgumentParser()
    parser.add_argument("--message-file", default="")
    parser.add_argument("--message-text", default="")
    parser.add_argument("--request-id", default="")
    parser.add_argument("--dry-run-parse", action="store_true")
    args = parser.parse_args()

    raw_text = str(args.message_text or "")
    if not raw_text and args.message_file:
        raw_text = Path(args.message_file).read_text(encoding="utf-8")
    if not raw_text and not sys.stdin.isatty():
        raw_text = sys.stdin.read()
    if not raw_text:
        print(json.dumps({"ok": False, "error_code": "empty_input"}, ensure_ascii=True))
        return 2

    if args.dry_run_parse:
        parsed = parse_openclaw_embedded_media_prompt(raw_text)
        print(json.dumps({"ok": True, "parsed": parsed}, ensure_ascii=True, separators=(",", ":")))
        return 0

    result = route_embedded_media_prompt_via_bridge(raw_text, request_id=(args.request_id or ""))
    print(json.dumps(result, ensure_ascii=True, separators=(",", ":")))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
