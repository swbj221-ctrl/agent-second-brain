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


def _proof_marker_from_parsed(parsed: dict[str, Any]) -> dict[str, Any]:
    return {
        "event": "openclaw_voice_dispatch_path_select",
        "selectedPath": "wrapper_cli_bridge",
        "branchReason": "embedded_audio_media_wrapper_redirect",
        "messageKind": str(parsed.get("media_kind") or ""),
        "mimeType": str(parsed.get("mime_type") or ""),
        "isAudioDocument": bool(parsed.get("is_audio_document")),
        "sourceModule": __file__,
    }


def _skip_marker_from_parsed(parsed: dict[str, Any]) -> dict[str, Any]:
    return {
        "event": "openclaw_voice_dispatch_path_select",
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
    parsed = voice_wrapper.parse_openclaw_embedded_media_prompt(raw_text)
    if not bool(parsed.get("is_audio_payload")):
        proof = _skip_marker_from_parsed(parsed)
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
    try:
        wrapper_call = _invoke_wrapper_cli(raw_text, request_id=request_id)
    except FileNotFoundError:
        error_marker = _wrapper_error_marker(parsed, "wrapper_cli_unavailable", "wrapper_script_missing")
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
        },
    }
    if not ok and not result["error_code"]:
        result["error_code"] = "wrapper_cli_failed"
    if not ok and not result["user_safe_text"]:
        result["user_safe_text"] = "Voice processing is temporarily unavailable. Please try again in a minute."
    if not ok and not wrapper_json.get("error_marker"):
        result["error_marker"] = _wrapper_error_marker(parsed, str(result["error_code"]), "wrapper_reported_failure")
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

    result = redirect_embedded_prompt(raw_text, request_id=str(args.request_id or ""))
    print(json.dumps(result, ensure_ascii=True, separators=(",", ":")))
    return 0 if result.get("ok") or (result.get("error_code") == "non_audio_media") else 1


if __name__ == "__main__":
    raise SystemExit(main())
