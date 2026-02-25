"""CLI helpers for OpenClaw to invoke d_brain actions."""

import argparse
import json

from d_brain.config import get_settings
from d_brain.integrations.health import get_health_snapshot
from d_brain.integrations.openclaw_bridge import dispatch_command, dispatch_command_response
from d_brain.ux_actions import (
    build_note_stub,
    build_plan_stub,
    build_reflection_stub,
    build_status_text,
)


def format_diag_text(snapshot: dict) -> str:
    checks = snapshot.get("checks") or {}
    mode = ((checks.get("openclaw_mode_expected") or {}).get("details") or {}).get(
        "transport_mode", "unknown"
    )
    workspace_ok = bool((checks.get("workspace_exists") or {}).get("ok"))
    bootstrap_ok = bool((checks.get("bootstrap_exists") or {}).get("ok"))
    heartbeat_ok = bool((checks.get("heartbeat_exists") or {}).get("ok"))
    poller = (checks.get("single_poller_guard") or {}).get("details") or {}
    conflict = bool(poller.get("conflict"))
    lines = [
        "DIAG",
        f"health_ok: {bool(snapshot.get('ok'))}",
        f"warnings: {len(snapshot.get('warnings') or [])}",
        f"errors: {len(snapshot.get('errors') or [])}",
        f"mode: {mode}",
        f"workspace: {'ok' if workspace_ok else 'fail'}",
        f"bootstrap: {'ok' if bootstrap_ok else 'fail'}",
        f"heartbeat: {'ok' if heartbeat_ok else 'fail'}",
        f"poller_conflict: {'yes' if conflict else 'no'}",
    ]
    if conflict:
        lines.append("hint: stop duplicate pollers and restart OpenClaw")
        for cmd in (poller.get("fix_commands") or [])[:2]:
            lines.append(f"cmd: {cmd}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="d_brain UX CLI")
    parser.add_argument(
        "action",
        choices=["status", "help", "plan", "note", "reflection", "command", "health", "diag"],
    )
    parser.add_argument("--user-id", type=int, default=0)
    parser.add_argument("--text", type=str, default="")
    parser.add_argument("--source-ref", type=str, default=None)
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()

    if args.action == "status":
        settings = get_settings()
        print(build_status_text(settings, args.user_id))
        return 0
    if args.action == "help":
        response_payload = dispatch_command_response(
            "/help",
            user_id=args.user_id,
            source_ref=args.source_ref,
        )
        print(str(response_payload.get("text") or "Help unavailable."))
        return 0 if response_payload.get("text") else 1
    if args.action == "plan":
        print(build_plan_stub())
        return 0
    if args.action == "note":
        print(build_note_stub())
        return 0
    if args.action == "reflection":
        print(build_reflection_stub())
        return 0
    if args.action == "command":
        response_payload = dispatch_command_response(
            args.text,
            user_id=args.user_id,
            source_ref=args.source_ref,
        )
        response = str(response_payload.get("text") or "")
        if not response:
            print("Unsupported command for bridge route.")
            return 1
        print(response)
        return 0
    if args.action == "health":
        if args.as_json:
            print(json.dumps(get_health_snapshot(), ensure_ascii=True))
            return 0
        response = dispatch_command(
            "/health",
            user_id=args.user_id,
            source_ref=args.source_ref,
        )
        print(response or "Health command unavailable.")
        return 0
    if args.action == "diag":
        snapshot = get_health_snapshot()
        if args.as_json:
            print(json.dumps(snapshot, ensure_ascii=True))
            return 0
        print(format_diag_text(snapshot))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
