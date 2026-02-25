"""OpenClaw e2e command smoke (OpenClaw adapter path, no aiogram polling)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def ensure_paths() -> Path:
    root = Path(__file__).resolve().parents[1]
    src = root / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    return root


def load_adapter(root: Path):
    adapter_path = root / "vault" / ".claude" / "skills" / "openclaw-main" / "adapter.py"
    spec = importlib.util.spec_from_file_location("openclaw_main_adapter", adapter_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load adapter: {adapter_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def emit(case: str, response: dict, extra: dict | None = None) -> None:
    payload = {
        "case": case,
        "status": response.get("status"),
        "route": response.get("route"),
        "text": str(response.get("text") or ""),
        "bridge_handled": bool((response.get("meta") or {}).get("bridge_handled")),
        "fallback_reason": str((response.get("meta") or {}).get("fallback_reason") or ""),
    }
    if extra:
        payload.update(extra)
    print(json.dumps(payload, ensure_ascii=True))


def main() -> int:
    root = ensure_paths()
    adapter = load_adapter(root)

    user_id = 123
    chat_id = 123
    commands = [
        ("help", "/help"),
        ("status", "/status"),
        ("plan_add", "/plan add e2e smoke plan"),
        ("plan_list", "/plan list"),
        ("plan_add_invalid", "/plan add"),
    ]
    for idx, (case, text) in enumerate(commands, start=1):
        message = {
            "text": text,
            "user_id": user_id,
            "chat_id": chat_id,
            "message_id": idx,
            "request_id": f"openclaw-e2e-command-{idx}",
        }
        response = adapter.main_handler_response(message)
        ok = bool(response.get("text"))
        if case == "plan_add_invalid":
            ok = ok and ("/plan add" in str(response.get("text") or ""))
        emit(case, response, {"ok": ok, "input": text})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
