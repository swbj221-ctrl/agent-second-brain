"""OpenClaw health snapshot smoke (JSONL, no network)."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any


def ensure_src_on_path() -> Path:
    root = Path(__file__).resolve().parents[1]
    src = root / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    return root


def emit(case: str, ok: bool, warnings: list[str], errors: list[str], summary: str) -> None:
    print(
        json.dumps(
            {
                "case": case,
                "ok": bool(ok),
                "warnings": warnings,
                "errors": errors,
                "summary": summary,
            },
            ensure_ascii=True,
        )
    )


class PatchSet:
    def __init__(self) -> None:
        self._items: list[tuple[Any, str, Any]] = []

    def set(self, obj: Any, attr: str, value: Any) -> None:
        self._items.append((obj, attr, getattr(obj, attr)))
        setattr(obj, attr, value)

    def restore(self) -> None:
        for obj, attr, old in reversed(self._items):
            setattr(obj, attr, old)


def _fake_bridge_module() -> Any:
    return SimpleNamespace(
        dispatch_command=lambda *args, **kwargs: None,
        dispatch_voice=lambda *args, **kwargs: None,
        dispatch_voice_from_message=lambda *args, **kwargs: None,
    )


def _build_fake_settings(root: Path, *, telegram_disabled: bool = True) -> Any:
    return SimpleNamespace(
        telegram_bot_token="dummy",
        openai_api_key="dummy",
        deepgram_api_key="",
        stt_provider="deepgram",
        tts_provider="none",
        telegram_disabled=telegram_disabled,
        vault_path=(root / "vault"),
    )


def run_case(
    *,
    case: str,
    create_bootstrap: bool,
    create_heartbeat: bool,
    telegram_disabled: bool,
) -> bool:
    from d_brain.integrations import health as health_mod  # noqa: WPS433

    with tempfile.TemporaryDirectory(prefix="oc-health-smoke-") as tmp:
        root = Path(tmp)
        workspace = root / ".openclaw" / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        (root / "vault").mkdir(parents=True, exist_ok=True)
        if create_bootstrap:
            (workspace / "bootstrap.md").write_text("# bootstrap\n", encoding="utf-8")
        if create_heartbeat:
            (workspace / "heartbeat.md").write_text("# heartbeat\n", encoding="utf-8")

        patch = PatchSet()
        try:
            patch.set(health_mod, "_repo_root", lambda: root)
            patch.set(health_mod, "get_settings", lambda: _build_fake_settings(root, telegram_disabled=telegram_disabled))
            patch.set(health_mod, "validate_settings", lambda settings: ([], []))
            patch.set(
                health_mod,
                "_detect_single_poller_guard",
                lambda: {
                    "supported": True,
                    "python_d_brain_seen": False,
                    "openclaw_gateway_seen": False,
                    "conflict": False,
                    "hint": "smoke",
                    "fix_commands": [],
                },
            )
            patch.set(
                health_mod.importlib,
                "import_module",
                lambda name: _fake_bridge_module()
                if name == "d_brain.integrations.openclaw_bridge"
                else __import__(name),
            )
            snap = health_mod.get_health_snapshot()
        finally:
            patch.restore()

        errors = [str(item) for item in (snap.get("errors") or [])]
        warnings = [str(item) for item in (snap.get("warnings") or [])]
        summary = (
            f"ok={bool(snap.get('ok'))} warnings={len(warnings)} errors={len(errors)} "
            f"mode={'openclaw' if telegram_disabled else 'local_aiogram_requested'}"
        )

        ok = False
        if case == "healthy_minimal":
            ok = bool(snap.get("ok")) and not errors
        elif case == "missing_bootstrap":
            ok = (not bool(snap.get("ok"))) and ("bootstrap_missing" in errors)
        elif case == "telegram_disabled_false_warn":
            ok = ("telegram_disabled_false" in warnings) and ("openclaw_mode_expected" in (snap.get("checks") or {}))

        emit(case, ok, warnings, errors, summary)
        return ok


def main() -> int:
    ensure_src_on_path()
    results = [
        run_case(case="healthy_minimal", create_bootstrap=True, create_heartbeat=True, telegram_disabled=True),
        run_case(case="missing_bootstrap", create_bootstrap=False, create_heartbeat=True, telegram_disabled=True),
        run_case(case="telegram_disabled_false_warn", create_bootstrap=True, create_heartbeat=True, telegram_disabled=False),
    ]
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
