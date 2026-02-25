"""Offline production readiness checks for OpenClaw-first runtime."""

from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path
from typing import Any


def _record(name: str, status: str, detail: str = "") -> dict[str, str]:
    return {"check": name, "status": status, "detail": detail}


def main() -> int:
    root = Path(".").resolve()
    src = root / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    records: list[dict[str, str]] = []
    warnings = 0
    failures = 0

    try:
        from d_brain.config import get_settings, validate_settings

        settings = get_settings()
        errors, warns = validate_settings(settings)
        if settings.telegram_disabled:
            records.append(_record("telegram_transport_owner", "PASS", "OpenClaw owns Telegram transport"))
        else:
            failures += 1
            records.append(_record("telegram_transport_owner", "FAIL", "D_BRAIN_TELEGRAM_DISABLED is false"))

        default_env = os.getenv("D_BRAIN_TELEGRAM_DISABLED")
        if default_env is None:
            records.append(
                _record(
                    "telegram_disabled_env",
                    "WARN",
                    "Env var not set in current shell; config default may still be true",
                )
            )
            warnings += 1
        else:
            records.append(
                _record(
                    "telegram_disabled_env",
                    "PASS" if default_env.strip().lower() in {"1", "true", "yes", "on"} else "WARN",
                    f"D_BRAIN_TELEGRAM_DISABLED={default_env}",
                )
            )
            if default_env.strip().lower() not in {"1", "true", "yes", "on"}:
                warnings += 1

        if errors:
            failures += 1
            records.append(_record("settings_validation_errors", "FAIL", "; ".join(errors[:3])))
        else:
            records.append(_record("settings_validation_errors", "PASS", "none"))
        if warns:
            warnings += 1
            records.append(_record("settings_validation_warnings", "WARN", "; ".join(warns[:3])))
        else:
            records.append(_record("settings_validation_warnings", "PASS", "none"))
    except Exception as exc:
        failures += 1
        records.append(_record("config_import", "FAIL", f"{type(exc).__name__}: {exc}"))
        settings = None  # type: ignore[assignment]

    for mod_name in (
        "d_brain.integrations.openclaw_bridge",
        "d_brain.integrations.openclaw_bridge.dispatch_command",
        "d_brain.integrations.openclaw_bridge.dispatch_voice",
        "d_brain.integrations.health",
    ):
        if mod_name.count(".") >= 2 and mod_name.endswith(("dispatch_command", "dispatch_voice")):
            module_name, attr_name = mod_name.rsplit(".", 1)
            try:
                module = importlib.import_module(module_name)
                ok = callable(getattr(module, attr_name, None))
                if ok:
                    records.append(_record(mod_name, "PASS", "callable"))
                else:
                    failures += 1
                    records.append(_record(mod_name, "FAIL", "missing callable"))
            except Exception as exc:
                failures += 1
                records.append(_record(mod_name, "FAIL", f"{type(exc).__name__}: {exc}"))
        else:
            try:
                importlib.import_module(mod_name)
                records.append(_record(mod_name, "PASS", "import ok"))
            except Exception as exc:
                failures += 1
                records.append(_record(mod_name, "FAIL", f"{type(exc).__name__}: {exc}"))

    workspace = root / ".openclaw" / "workspace"
    records.append(_record("openclaw_workspace", "PASS" if workspace.exists() else "WARN", str(workspace)))
    if not workspace.exists():
        warnings += 1

    bootstrap_paths = [workspace / "BOOTSTRAP.md", workspace / "bootstrap.md"]
    heartbeat_paths = [workspace / "HEARTBEAT.md", workspace / "heartbeat.md"]
    bootstrap_found = next((p for p in bootstrap_paths if p.exists()), None)
    heartbeat_found = next((p for p in heartbeat_paths if p.exists()), None)
    if bootstrap_found:
        records.append(_record("workspace_bootstrap", "PASS", str(bootstrap_found.relative_to(root))))
    else:
        failures += 1
        records.append(_record("workspace_bootstrap", "FAIL", "BOOTSTRAP.md/bootstrap.md not found"))
    if heartbeat_found:
        records.append(_record("workspace_heartbeat", "PASS", str(heartbeat_found.relative_to(root))))
    else:
        failures += 1
        records.append(_record("workspace_heartbeat", "FAIL", "HEARTBEAT.md/heartbeat.md not found"))

    settings_obj = settings if "settings" in locals() else None
    main_reasoning_openai = bool(
        settings_obj and str(getattr(settings_obj, "model_route_main_reasoning_provider", "")).strip().lower() == "openai"
    )
    voice_reasoning_openai = bool(
        settings_obj and str(getattr(settings_obj, "model_route_voice_reasoning_provider", "")).strip().lower() == "openai"
    )
    stt_deepgram_enabled = bool(
        settings_obj and str(getattr(settings_obj, "stt_provider", "")).strip().lower() == "deepgram"
    )
    tts_deepgram_enabled = bool(
        settings_obj and str(getattr(settings_obj, "tts_provider", "")).strip().lower() == "deepgram"
    )
    local_aiogram_enabled = bool(settings_obj and (getattr(settings_obj, "telegram_disabled", True) is False))

    # Warn-only env guidance for enabled features only.
    for env_name, required_for, condition in (
        ("OPENAI_API_KEY", "main/voice reasoning routes", main_reasoning_openai or voice_reasoning_openai),
        ("DEEPGRAM_API_KEY", "STT/TTS when Deepgram is enabled", stt_deepgram_enabled or tts_deepgram_enabled),
        ("TELEGRAM_BOT_TOKEN", "local aiogram polling only", local_aiogram_enabled),
    ):
        if not condition:
            records.append(_record(f"env:{env_name}", "PASS", f"not required ({required_for} disabled)"))
            continue
        present = bool(os.getenv(env_name, "").strip())
        status = "PASS" if present else "WARN"
        if not present:
            warnings += 1
        records.append(_record(f"env:{env_name}", status, required_for))

    summary_status = "PASS"
    if failures:
        summary_status = "FAIL"
    elif warnings:
        summary_status = "WARN"

    for row in records:
        print(json.dumps(row, ensure_ascii=True))
    print(
        json.dumps(
            {
                "summary": {
                    "status": summary_status,
                    "pass": sum(1 for r in records if r["status"] == "PASS"),
                    "warn": sum(1 for r in records if r["status"] == "WARN"),
                    "fail": sum(1 for r in records if r["status"] == "FAIL"),
                }
            },
            ensure_ascii=True,
        )
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
