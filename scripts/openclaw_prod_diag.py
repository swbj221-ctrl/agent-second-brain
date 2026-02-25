"""OpenClaw-first production diagnostics (no network calls)."""

from __future__ import annotations

import importlib
import json
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any


def ensure_src_on_path() -> Path:
    root = Path(__file__).resolve().parents[1]
    src = root / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    return root


def emit_jsonl(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=True))


def emit_check(name: str, ok: bool, details: dict[str, Any] | None = None) -> None:
    emit_jsonl(
        {
            "check": name,
            "ok": bool(ok),
            "details": details or {},
        }
    )


def _port_in_use(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.2):
            return True
    except OSError:
        return False


def _find_process_hints() -> dict[str, Any]:
    if os.name != "nt":
        return {"supported": False}
    try:
        output = subprocess.run(
            ["tasklist"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        text = (output.stdout or "").lower()
        return {
            "supported": True,
            "openclaw_process_seen": ("openclaw" in text),
            "python_process_seen": ("python" in text),
        }
    except Exception as exc:
        return {"supported": False, "error": f"{exc.__class__.__name__}:{exc}"}


def main() -> int:
    root = ensure_src_on_path()
    failures = 0

    # Config load + validation
    try:
        from d_brain.config import get_settings, validate_settings  # noqa: WPS433

        settings = get_settings()
        errors, warnings = validate_settings(settings)
        ok = len(errors) == 0
        emit_check(
            "config_sanity",
            ok,
            {
                "errors_count": len(errors),
                "warnings_count": len(warnings),
                "errors": errors[:10],
                "warnings": warnings[:10],
            },
        )
        if not ok:
            failures += 1
    except Exception as exc:
        emit_check("config_sanity", False, {"error": f"{exc.__class__.__name__}:{exc}"})
        return 1

    # OpenClaw-first guardrail
    emit_check(
        "telegram_disabled_flag",
        bool(settings.telegram_disabled),
        {
            "telegram_disabled": bool(settings.telegram_disabled),
            "transport_mode": "openclaw" if settings.telegram_disabled else "local_aiogram_requested",
        },
    )
    if not settings.telegram_disabled:
        failures += 1

    # Required keys (presence only, no secret values)
    emit_check(
        "required_keys_presence",
        bool(os.getenv("TELEGRAM_BOT_TOKEN", "").strip()),
        {
            "TELEGRAM_BOT_TOKEN_present": bool(os.getenv("TELEGRAM_BOT_TOKEN", "").strip()),
            "OPENAI_API_KEY_present": bool(os.getenv("OPENAI_API_KEY", "").strip()),
            "DEEPGRAM_API_KEY_present": bool(os.getenv("DEEPGRAM_API_KEY", "").strip()),
        },
    )
    if not os.getenv("TELEGRAM_BOT_TOKEN", "").strip():
        failures += 1

    # OpenClaw CLI PATH sanity
    openclaw_path = shutil.which("openclaw")
    emit_check(
        "openclaw_path",
        bool(openclaw_path),
        {"openclaw_in_path": bool(openclaw_path), "path": openclaw_path or ""},
    )
    if not openclaw_path:
        failures += 1

    # Workspace BOOTSTRAP/HEARTBEAT presence (prefer lowercase; report both)
    workspace_dir = root / ".openclaw" / "workspace"
    bootstrap_upper = workspace_dir / "BOOTSTRAP.md"
    heartbeat_upper = workspace_dir / "HEARTBEAT.md"
    bootstrap_lower = workspace_dir / "bootstrap.md"
    heartbeat_lower = workspace_dir / "heartbeat.md"
    has_bootstrap = bootstrap_lower.exists() or bootstrap_upper.exists()
    has_heartbeat = heartbeat_lower.exists() or heartbeat_upper.exists()
    emit_check(
        "workspace_bootstrap_heartbeat",
        has_bootstrap and has_heartbeat,
        {
            "workspace_dir": str(workspace_dir),
            "bootstrap_lower": bootstrap_lower.exists(),
            "bootstrap_upper": bootstrap_upper.exists(),
            "heartbeat_lower": heartbeat_lower.exists(),
            "heartbeat_upper": heartbeat_upper.exists(),
        },
    )
    if not (has_bootstrap and has_heartbeat):
        failures += 1

    # Bridge import smoke
    try:
        bridge = importlib.import_module("d_brain.integrations.openclaw_bridge")
        ok = all(
            hasattr(bridge, name)
            for name in ("dispatch_command", "dispatch_voice", "dispatch_voice_from_message")
        )
        emit_check(
            "bridge_import_smoke",
            ok,
            {
                "module": "d_brain.integrations.openclaw_bridge",
                "dispatch_command": hasattr(bridge, "dispatch_command"),
                "dispatch_voice": hasattr(bridge, "dispatch_voice"),
                "dispatch_voice_from_message": hasattr(bridge, "dispatch_voice_from_message"),
            },
        )
        if not ok:
            failures += 1
    except Exception as exc:
        emit_check("bridge_import_smoke", False, {"error": f"{exc.__class__.__name__}:{exc}"})
        failures += 1

    # Duplicate poller risk hints (non-authoritative)
    proc_hints = _find_process_hints()
    emit_check(
        "duplicate_poller_risk_hints",
        True,
        {
            **proc_hints,
            "telegram_disabled": bool(settings.telegram_disabled),
            "risk_hint": (
                "low" if settings.telegram_disabled else "high_local_polling_requested"
            ),
        },
    )

    # Gateway port hint (18789 used by local OpenClaw stack scripts)
    port_busy = _port_in_use(18789)
    emit_check(
        "gateway_port_18789",
        True,
        {"port": 18789, "busy": bool(port_busy)},
    )

    emit_jsonl({"summary": {"ok": failures == 0, "failures": failures}})
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
