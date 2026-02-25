"""Ops helpers smoke (no network, JSONL)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


def ensure_paths() -> Path:
    root = Path(__file__).resolve().parents[1]
    src = root / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    return root


def emit(case: str, ok: bool, **payload: Any) -> None:
    print(json.dumps({"case": case, "ok": bool(ok), **payload}, ensure_ascii=True))


def load_ux_cli(root: Path):
    path = root / "scripts" / "ux_cli.py"
    spec = importlib.util.spec_from_file_location("ux_cli_ops_smoke", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def case_ops_scripts_exist(root: Path) -> bool:
    expected = [
        "start-openclaw.ps1",
        "stop-openclaw.ps1",
        "restart-openclaw.ps1",
        "status-openclaw.ps1",
        "fix-path-node-openclaw.ps1",
        "kill-telegram-conflicts.ps1",
        "fix-openclaw-acl.ps1",
    ]
    missing = [name for name in expected if not (root / "ops" / name).exists()]
    ok = not missing
    emit("ops_scripts_exist", ok, missing=missing)
    return ok


def case_health_diag_import_ok() -> bool:
    from d_brain.integrations.health import get_health_snapshot  # noqa: WPS433
    from d_brain.integrations.openclaw_bridge import handle_diag  # noqa: WPS433

    ok = callable(get_health_snapshot) and callable(handle_diag)
    emit("health_diag_import_ok", ok, health_callable=callable(get_health_snapshot), diag_callable=callable(handle_diag))
    return ok


def case_cli_diag_formatter_text(root: Path) -> bool:
    mod = load_ux_cli(root)
    snapshot = {
        "ok": True,
        "warnings": ["single_poller_conflict_risk"],
        "errors": [],
        "checks": {
            "workspace_exists": {"ok": True, "details": {}},
            "bootstrap_exists": {"ok": True, "details": {}},
            "heartbeat_exists": {"ok": True, "details": {}},
            "openclaw_mode_expected": {"ok": True, "details": {"transport_mode": "openclaw"}},
            "single_poller_guard": {
                "ok": False,
                "details": {
                    "conflict": True,
                    "fix_commands": ["Stop-Process -Name python -Force", "Stop-Process -Name openclaw -Force"],
                },
            },
        },
    }
    text = mod.format_diag_text(snapshot)
    ok = isinstance(text, str) and ("DIAG" in text) and ("poller_conflict: yes" in text)
    emit("cli_diag_formatter_text", ok, length=len(text), preview=text.splitlines()[:4])
    return ok


def main() -> int:
    root = ensure_paths()
    results = [
        case_ops_scripts_exist(root),
        case_health_diag_import_ok(),
        case_cli_diag_formatter_text(root),
    ]
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())

