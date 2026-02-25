"""Transport-agnostic health snapshot helpers (no network calls)."""

from __future__ import annotations

import importlib
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from d_brain.config import get_settings, validate_settings


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _first_existing(paths: list[Path]) -> Path | None:
    for path in paths:
        if path.exists():
            return path
    return None


def _add_check(
    checks: dict[str, dict[str, Any]],
    *,
    name: str,
    ok: bool,
    **details: Any,
) -> None:
    checks[name] = {
        "ok": bool(ok),
        "details": details,
    }


def _poller_conflict_remediation_commands() -> list[str]:
    return [
        "Get-Process -Name python,openclaw -ErrorAction SilentlyContinue",
        "Stop-Process -Name python -Force",
        "Stop-Process -Name openclaw -Force",
        "powershell -ExecutionPolicy Bypass -File ops\\restart-openclaw.ps1",
    ]


def _detect_single_poller_guard() -> dict[str, Any]:
    """Best-effort local process hinting for duplicate pollers on Windows."""
    details: dict[str, Any] = {
        "supported": (os.name == "nt"),
        "python_d_brain_seen": False,
        "openclaw_gateway_seen": False,
        "conflict": False,
        "hint": "",
        "fix_commands": _poller_conflict_remediation_commands(),
    }
    if os.name != "nt":
        details["hint"] = "process_check_unsupported_platform"
        return details

    ps = (
        "$ErrorActionPreference='SilentlyContinue'; "
        "$items = Get-CimInstance Win32_Process | "
        "Where-Object { $_.Name -match '^(python(\\.exe)?|openclaw(\\.exe)?)$' } | "
        "Select-Object Name,ProcessId,CommandLine; "
        "$items | ConvertTo-Json -Compress"
    )
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        raw = (proc.stdout or "").strip()
        if not raw:
            details["hint"] = "no_relevant_processes_seen"
            return details
        import json as _json  # local import to avoid top-level rename churn

        parsed = _json.loads(raw)
        rows = parsed if isinstance(parsed, list) else [parsed]
        for row in rows:
            name = str((row or {}).get("Name") or "").lower()
            cmd = str((row or {}).get("CommandLine") or "").lower()
            if "python" in name and ("d_brain" in cmd):
                details["python_d_brain_seen"] = True
            if "openclaw" in name and (" gateway" in cmd or cmd.endswith("gateway")):
                details["openclaw_gateway_seen"] = True
        details["conflict"] = bool(
            details["python_d_brain_seen"] and details["openclaw_gateway_seen"]
        )
        details["hint"] = (
            "duplicate_poller_detected" if details["conflict"] else "no_duplicate_poller_signature"
        )
        return details
    except Exception as exc:
        details["hint"] = f"process_check_failed:{exc.__class__.__name__}"
        return details


def get_health_snapshot() -> dict[str, Any]:
    """Return a local-only health snapshot for OpenClaw-first operation."""
    checks: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []
    errors: list[str] = []
    timestamp = datetime.now(timezone.utc).isoformat()

    root = _repo_root()
    workspace = root / ".openclaw" / "workspace"
    bootstrap_path = _first_existing([workspace / "BOOTSTRAP.md", workspace / "bootstrap.md"])
    heartbeat_path = _first_existing([workspace / "HEARTBEAT.md", workspace / "heartbeat.md"])

    _add_check(
        checks,
        name="workspace_exists",
        ok=workspace.exists() and workspace.is_dir(),
        path=str(workspace),
    )
    if not (workspace.exists() and workspace.is_dir()):
        errors.append("workspace_missing")

    _add_check(
        checks,
        name="bootstrap_exists",
        ok=bootstrap_path is not None,
        path=str(bootstrap_path or (workspace / "BOOTSTRAP.md")),
    )
    if bootstrap_path is None:
        errors.append("bootstrap_missing")

    _add_check(
        checks,
        name="heartbeat_exists",
        ok=heartbeat_path is not None,
        path=str(heartbeat_path or (workspace / "HEARTBEAT.md")),
    )
    if heartbeat_path is None:
        errors.append("heartbeat_missing")

    settings = None
    try:
        settings = get_settings()
        cfg_errors, cfg_warnings = validate_settings(settings)
        _add_check(
            checks,
            name="config_loaded",
            ok=True,
            warnings_count=len(cfg_warnings),
            errors_count=len(cfg_errors),
        )
        warnings.extend(str(item) for item in cfg_warnings)
        if cfg_errors:
            errors.extend(str(item) for item in cfg_errors)
    except Exception as exc:
        _add_check(
            checks,
            name="config_loaded",
            ok=False,
            error=f"{exc.__class__.__name__}:{exc}",
        )
        errors.append("config_load_failed")

    try:
        bridge = importlib.import_module("d_brain.integrations.openclaw_bridge")
        ok = all(
            hasattr(bridge, attr)
            for attr in ("dispatch_command", "dispatch_voice", "dispatch_voice_from_message")
        )
        _add_check(
            checks,
            name="bridge_import_ok",
            ok=ok,
            dispatch_command=hasattr(bridge, "dispatch_command"),
            dispatch_voice=hasattr(bridge, "dispatch_voice"),
            dispatch_voice_from_message=hasattr(bridge, "dispatch_voice_from_message"),
        )
        if not ok:
            errors.append("bridge_import_incomplete")
    except Exception as exc:
        _add_check(
            checks,
            name="bridge_import_ok",
            ok=False,
            error=f"{exc.__class__.__name__}:{exc}",
        )
        errors.append("bridge_import_failed")

    if settings is not None:
        vault_exists = settings.vault_path.exists() and settings.vault_path.is_dir()
        _add_check(
            checks,
            name="vault_path_exists",
            ok=vault_exists,
            path=str(settings.vault_path),
        )
        if not vault_exists:
            errors.append("vault_path_missing")

        _add_check(
            checks,
            name="openclaw_mode_expected",
            ok=bool(settings.telegram_disabled),
            telegram_disabled=bool(settings.telegram_disabled),
            transport_mode="openclaw" if settings.telegram_disabled else "local_aiogram_requested",
        )
        if not settings.telegram_disabled:
            warnings.append("telegram_disabled_false")

        provider_flags = {
            "openai_ready": bool(settings.openai_api_key.strip()),
            "stt_provider": settings.stt_provider,
            "stt_ready": (
                settings.stt_provider.strip().lower() != "deepgram"
                or bool(settings.deepgram_api_key.strip())
            ),
            "tts_provider": settings.tts_provider,
            "tts_ready": (
                settings.tts_provider.strip().lower() in {"", "none", "mock"}
                or bool(settings.deepgram_api_key.strip())
            ),
            "telegram_token_present": bool(settings.telegram_bot_token.strip()),
        }
        _add_check(checks, name="provider_readiness", ok=True, **provider_flags)

        poller = _detect_single_poller_guard()
        guard_ok = bool(settings.telegram_disabled) and (not bool(poller.get("conflict")))
        _add_check(checks, name="single_poller_guard", ok=guard_ok, **poller)
        if poller.get("conflict"):
            warnings.append("single_poller_conflict_risk")
    else:
        _add_check(checks, name="vault_path_exists", ok=False, reason="config_unavailable")
        _add_check(checks, name="openclaw_mode_expected", ok=False, reason="config_unavailable")
        _add_check(checks, name="provider_readiness", ok=False, reason="config_unavailable")
        _add_check(checks, name="single_poller_guard", ok=False, reason="config_unavailable")

    return {
        "ok": len(errors) == 0,
        "checks": checks,
        "warnings": warnings,
        "errors": errors,
        "timestamp": timestamp,
    }
