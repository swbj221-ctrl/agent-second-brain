"""Wrapper-first redirect shim for OpenClaw embedded Telegram media prompts.

Purpose:
- Detect embedded Telegram audio/voice/audio-document prompts in the project workspace layer
- Emit proof/error markers for the redirect decision
- Invoke the existing wrapper CLI (`openclaw_live_voice_bridge_cli.py`) as the only bridge route
- Avoid silent fallback to direct STT/Deepgram exec
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import openclaw_live_voice_bridge_cli as voice_wrapper  # type: ignore


def _safe_preview(text: str, max_len: int = 180) -> str:
    compact = " ".join((text or "").split())
    return compact if len(compact) <= max_len else compact[:max_len] + "...<trimmed>"


def _canonical_request_id(value: Any = None, *, payload: dict[str, Any] | None = None) -> str:
    direct = str(value or "").strip()
    if direct:
        return direct
    if isinstance(payload, dict):
        for key in ("requestId", "request_id"):
            candidate = str(payload.get(key) or "").strip()
            if candidate:
                return candidate
    return ""


def _proof_marker_from_parsed(parsed: dict[str, Any]) -> dict[str, Any]:
    return {
        "event": "openclaw_voice_dispatch_path_select",
        "traceStage": "redirect.path_select",
        "selectedPath": "wrapper_cli_bridge",
        "branchReason": "embedded_audio_media_wrapper_redirect",
        "messageKind": str(parsed.get("media_kind") or ""),
        "mimeType": str(parsed.get("mime_type") or ""),
        "isAudioDocument": bool(parsed.get("is_audio_document")),
        "sourceModule": __file__,
    }


def _emit_marker_visible(marker: dict[str, Any] | None) -> None:
    if not isinstance(marker, dict):
        return
    line = ""
    try:
        line = json.dumps(marker, ensure_ascii=True, separators=(",", ":"))
    except Exception:
        return
    for stream in (sys.stderr, sys.stdout):
        try:
            print(line, file=stream, flush=True)
        except Exception:
            pass


def _skip_marker_from_parsed(parsed: dict[str, Any]) -> dict[str, Any]:
    return {
        "event": "openclaw_voice_dispatch_path_select",
        "traceStage": "redirect.path_skip",
        "selectedPath": "embedded_default_flow",
        "branchReason": "non_audio_media_or_text",
        "messageKind": str(parsed.get("media_kind") or ""),
        "mimeType": str(parsed.get("mime_type") or ""),
        "isAudioDocument": bool(parsed.get("is_audio_document")),
        "sourceModule": __file__,
    }


def _wrapper_error_marker(parsed: dict[str, Any], error_code: str, branch_reason: str) -> dict[str, Any]:
    return {
        "event": "openclaw_voice_dispatch_path_error",
        "traceStage": "redirect.path_error",
        "selectedPath": "none",
        "intendedPath": "wrapper_cli_bridge",
        "errorCode": error_code,
        "branchReason": branch_reason,
        "messageKind": str(parsed.get("media_kind") or ""),
        "mimeType": str(parsed.get("mime_type") or ""),
        "isAudioDocument": bool(parsed.get("is_audio_document")),
        "sourceModule": __file__,
    }


def _invoke_wrapper_cli(raw_text: str, request_id: str = "") -> dict[str, Any]:
    wrapper_path = SCRIPTS_DIR / "openclaw_live_voice_bridge_cli.py"
    cmd = [sys.executable, str(wrapper_path), "--message-text", raw_text]
    if request_id:
        cmd.extend(["--request-id", request_id])
    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    completed = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    stdout = (completed.stdout or "").strip()
    stderr = (completed.stderr or "").strip()
    parsed_json: dict[str, Any] | None = None
    if stdout:
        try:
            parsed_json = json.loads(stdout.splitlines()[-1])
        except Exception:
            parsed_json = None
    return {
        "returncode": int(completed.returncode),
        "stdout": stdout,
        "stderr": stderr,
        "json": parsed_json,
        "cmd": [str(c) for c in cmd[:3]] + ["--message-text", "<omitted>", *(["--request-id", request_id] if request_id else [])],
    }


def redirect_embedded_prompt(raw_text: str, *, request_id: str = "") -> dict[str, Any]:
    request_id = _canonical_request_id(request_id)
    parsed = voice_wrapper.parse_openclaw_embedded_media_prompt(raw_text)
    if not bool(parsed.get("is_audio_payload")):
        proof = _skip_marker_from_parsed(parsed)
        proof["requestId"] = request_id
        proof["request_id"] = request_id
        _emit_marker_visible(proof)
        return {
            "ok": False,
            "handled": False,
            "proof_marker": proof,
            "error_code": "non_audio_media",
            "user_safe_text": "",
            "wrapper_invoked": False,
            "wrapper_result": None,
            "parsed": {
                "messageKind": parsed.get("media_kind"),
                "mimeType": parsed.get("mime_type"),
                "isAudioDocument": bool(parsed.get("is_audio_document")),
                "preview": _safe_preview(str(raw_text or "")),
            },
        }

    proof = _proof_marker_from_parsed(parsed)
    proof["requestId"] = request_id
    proof["request_id"] = request_id
    _emit_marker_visible(proof)
    if not str(request_id or "").strip():
        error_marker = _wrapper_error_marker(parsed, "request_id_missing_in_chain", "redirect_missing_request_id")
        error_marker["requestId"] = ""
        error_marker["request_id"] = ""
        error_marker["stage"] = "redirect.path_select"
        _emit_marker_visible(error_marker)
        return {
            "ok": False,
            "handled": True,
            "proof_marker": proof,
            "error_marker": error_marker,
            "error_code": "request_id_missing_in_chain",
            "user_safe_text": "Voice processing is temporarily unavailable. Please try again in a minute.",
            "wrapper_invoked": False,
            "wrapper_result": None,
        }
    try:
        wrapper_call = _invoke_wrapper_cli(raw_text, request_id=request_id)
        if str(wrapper_call.get("stderr") or "").strip():
            try:
                print(str(wrapper_call.get("stderr") or ""), file=sys.stderr, flush=True)
            except Exception:
                pass
    except FileNotFoundError:
        error_marker = _wrapper_error_marker(parsed, "wrapper_cli_unavailable", "wrapper_script_missing")
        error_marker["requestId"] = request_id
        error_marker["request_id"] = request_id
        _emit_marker_visible(error_marker)
        return {
            "ok": False,
            "handled": True,
            "proof_marker": proof,
            "error_marker": error_marker,
            "error_code": "wrapper_cli_unavailable",
            "user_safe_text": "Voice processing is temporarily unavailable. Please try again in a minute.",
            "wrapper_invoked": False,
            "wrapper_result": None,
        }
    except Exception as exc:
        error_marker = _wrapper_error_marker(parsed, "wrapper_cli_exec_failed", "wrapper_exec_exception")
        error_marker["requestId"] = request_id
        error_marker["request_id"] = request_id
        _emit_marker_visible(error_marker)
        return {
            "ok": False,
            "handled": True,
            "proof_marker": proof,
            "error_marker": error_marker,
            "error_code": "wrapper_cli_exec_failed",
            "user_safe_text": "Voice processing is temporarily unavailable. Please try again in a minute.",
            "wrapper_invoked": False,
            "wrapper_result": {"errorDetail": f"{type(exc).__name__}:{str(exc)[:160]}"},
        }

    wrapper_json = wrapper_call.get("json")
    if not isinstance(wrapper_json, dict):
        error_marker = _wrapper_error_marker(parsed, "wrapper_cli_bad_output", "wrapper_non_json_output")
        error_marker["requestId"] = request_id
        error_marker["request_id"] = request_id
        _emit_marker_visible(error_marker)
        return {
            "ok": False,
            "handled": True,
            "proof_marker": proof,
            "error_marker": error_marker,
            "error_code": "wrapper_cli_bad_output",
            "user_safe_text": "Voice processing is temporarily unavailable. Please try again in a minute.",
            "wrapper_invoked": True,
            "wrapper_result": {
                "returncode": wrapper_call.get("returncode"),
                "stderr": _safe_preview(str(wrapper_call.get("stderr") or "")),
                "stdoutPreview": _safe_preview(str(wrapper_call.get("stdout") or "")),
            },
        }

    ok = bool(wrapper_json.get("ok"))
    wrapper_proof = wrapper_json.get("proof") if isinstance(wrapper_json.get("proof"), dict) else {}
    wrapper_selected_path = str(wrapper_proof.get("selectedPath") or "")
    if ok and wrapper_selected_path and wrapper_selected_path != "d_brain_openclaw_bridge":
        error_marker = _wrapper_error_marker(parsed, "wrapper_unexpected_non_bridge_path", "wrapper_reported_non_bridge_for_audio")
        error_marker["requestId"] = request_id
        error_marker["request_id"] = request_id
        _emit_marker_visible(error_marker)
        return {
            "ok": False,
            "handled": True,
            "proof_marker": proof,
            "error_marker": error_marker,
            "error_code": "wrapper_unexpected_non_bridge_path",
            "user_safe_text": "Voice processing path mismatch detected. Please try again in a minute.",
            "wrapper_invoked": True,
            "wrapper_result": {
                "returncode": wrapper_call.get("returncode"),
                "wrapper_proof": wrapper_proof,
                "wrapper_error_marker": wrapper_json.get("error_marker"),
                "wrapper_error_code": wrapper_json.get("error_code"),
                "adapter_response": wrapper_json.get("adapter_response"),
                "trace": wrapper_json.get("trace"),
            },
        }
    result: dict[str, Any] = {
        "ok": ok,
        "handled": True,
        "proof_marker": proof,
        "error_code": str(wrapper_json.get("error_code") or ""),
        "user_safe_text": str(wrapper_json.get("user_safe_text") or ""),
        "wrapper_invoked": True,
        "wrapper_result": {
            "returncode": wrapper_call.get("returncode"),
            "wrapper_proof": wrapper_json.get("proof"),
            "wrapper_error_marker": wrapper_json.get("error_marker"),
            "wrapper_error_code": wrapper_json.get("error_code"),
            "adapter_response": wrapper_json.get("adapter_response"),
            "trace": wrapper_json.get("trace"),
        },
    }
    if not ok and not result["error_code"]:
        result["error_code"] = "wrapper_cli_failed"
    if not ok and not result["user_safe_text"]:
        result["user_safe_text"] = "Voice processing is temporarily unavailable. Please try again in a minute."
    if not ok and not wrapper_json.get("error_marker"):
        result["error_marker"] = _wrapper_error_marker(parsed, str(result["error_code"]), "wrapper_reported_failure")
    if isinstance(result.get("error_marker"), dict):
        result["error_marker"]["requestId"] = request_id
        result["error_marker"]["request_id"] = request_id
        _emit_marker_visible(result["error_marker"])
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--message-file", default="")
    parser.add_argument("--message-text", default="")
    parser.add_argument("--request-id", default="")
    args = parser.parse_args()

    raw_text = str(args.message_text or "")
    if not raw_text and args.message_file:
        raw_text = Path(args.message_file).read_text(encoding="utf-8")
    if not raw_text and not sys.stdin.isatty():
        raw_text = sys.stdin.read()
    if not raw_text:
        print(json.dumps({"ok": False, "error_code": "empty_input"}, ensure_ascii=True))
        return 2

    result = redirect_embedded_prompt(raw_text, request_id=_canonical_request_id(args.request_id))
    print(json.dumps(result, ensure_ascii=True, separators=(",", ":")))
    return 0 if result.get("ok") or (result.get("error_code") == "non_audio_media") else 1


if __name__ == "__main__":
    raise SystemExit(main())
