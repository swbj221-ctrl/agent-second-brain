"""Transport-agnostic heartbeat/cron runner for OpenClaw integration."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from d_brain.config import Settings, get_settings
from d_brain.integrations.openclaw_outbound import build_openclaw_outbound
from d_brain.services.model_routing import TASK_CRON_SUMMARY, resolve_provider_for_task
from d_brain.services.sidecar_client import call_sidecar_action

logger = logging.getLogger(__name__)

JOB_HEARTBEAT_TICK = "heartbeat.tick"
JOB_DIGEST_DAILY = "digest.daily"

HEARTBEAT_INTERVAL_MIN = 5
HEARTBEAT_INTERVAL_MAX = 240
_TIME_PATTERN = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_scheduler_config(settings: Settings) -> dict[str, Any]:
    return {
        "heartbeat": {
            "enabled": bool(settings.scheduler_heartbeat_enabled_default),
            "interval_minutes": int(settings.scheduler_heartbeat_interval_minutes_default),
        },
        "digest": {
            "enabled": bool(settings.scheduler_digest_enabled_default),
            "time": settings.scheduler_digest_daily_time_default,
        },
    }


def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_state_for_settings(settings: Settings) -> dict[str, Any]:
    return _load_state(settings.heartbeat_state_path)


def _save_state_for_settings(settings: Settings, state: dict[str, Any]) -> None:
    _save_state(settings.heartbeat_state_path, state)


def get_scheduler_config(settings: Settings | None = None) -> dict[str, Any]:
    active_settings = settings or get_settings()
    state = _load_state_for_settings(active_settings)
    defaults = _default_scheduler_config(active_settings)
    raw = state.get("scheduler_config") or {}
    heartbeat_raw = (raw.get("heartbeat") or {}) if isinstance(raw, dict) else {}
    digest_raw = (raw.get("digest") or {}) if isinstance(raw, dict) else {}

    interval = heartbeat_raw.get("interval_minutes", defaults["heartbeat"]["interval_minutes"])
    if not isinstance(interval, int):
        interval = defaults["heartbeat"]["interval_minutes"]
    interval = max(HEARTBEAT_INTERVAL_MIN, min(HEARTBEAT_INTERVAL_MAX, int(interval)))

    digest_time = digest_raw.get("time", defaults["digest"]["time"])
    digest_time = str(digest_time)
    if not _TIME_PATTERN.match(digest_time):
        digest_time = defaults["digest"]["time"]

    return {
        "heartbeat": {
            "enabled": bool(heartbeat_raw.get("enabled", defaults["heartbeat"]["enabled"])),
            "interval_minutes": interval,
        },
        "digest": {
            "enabled": bool(digest_raw.get("enabled", defaults["digest"]["enabled"])),
            "time": digest_time,
        },
    }


def _set_scheduler_config(config: dict[str, Any], settings: Settings) -> dict[str, Any]:
    state = _load_state_for_settings(settings)
    state["scheduler_config"] = config
    _save_state_for_settings(settings, state)
    return config


def set_heartbeat_interval(minutes: int, settings: Settings | None = None) -> dict[str, Any]:
    active_settings = settings or get_settings()
    if minutes < HEARTBEAT_INTERVAL_MIN or minutes > HEARTBEAT_INTERVAL_MAX:
        return {
            "ok": False,
            "error": "interval_out_of_range",
            "min": HEARTBEAT_INTERVAL_MIN,
            "max": HEARTBEAT_INTERVAL_MAX,
        }
    config = get_scheduler_config(active_settings)
    config["heartbeat"]["interval_minutes"] = int(minutes)
    _set_scheduler_config(config, active_settings)
    return {"ok": True, "config": config}


def set_heartbeat_enabled(enabled: bool, settings: Settings | None = None) -> dict[str, Any]:
    active_settings = settings or get_settings()
    config = get_scheduler_config(active_settings)
    config["heartbeat"]["enabled"] = bool(enabled)
    _set_scheduler_config(config, active_settings)
    return {"ok": True, "config": config}


def set_digest_enabled(enabled: bool, settings: Settings | None = None) -> dict[str, Any]:
    active_settings = settings or get_settings()
    config = get_scheduler_config(active_settings)
    config["digest"]["enabled"] = bool(enabled)
    _set_scheduler_config(config, active_settings)
    return {"ok": True, "config": config}


def set_digest_time(time_hhmm: str, settings: Settings | None = None) -> dict[str, Any]:
    active_settings = settings or get_settings()
    if not _TIME_PATTERN.match(time_hhmm):
        return {"ok": False, "error": "invalid_time"}
    config = get_scheduler_config(active_settings)
    config["digest"]["time"] = time_hhmm
    _set_scheduler_config(config, active_settings)
    return {"ok": True, "config": config}


def build_job_specs(settings: Settings | None = None) -> list[dict[str, Any]]:
    active_settings = settings or get_settings()
    config = get_scheduler_config(active_settings)
    return [
        {
            "name": JOB_HEARTBEAT_TICK,
            "enabled": bool(config["heartbeat"]["enabled"]),
            "schedule_kind": "interval_minutes",
            "schedule_value": int(config["heartbeat"]["interval_minutes"]),
            "provider_role": "heartbeat",
            "description": "Run one heartbeat tick",
        },
        {
            "name": JOB_DIGEST_DAILY,
            "enabled": bool(config["digest"]["enabled"]),
            "schedule_kind": "daily_time",
            "schedule_value": str(config["digest"]["time"]),
            "provider_role": "cron",
            "description": "Run daily digest placeholder",
        },
    ]


def record_scheduler_sync(
    *,
    settings: Settings | None = None,
    trigger_source: str,
    execution_mode: str,
    status: str,
    synced_jobs: list[dict[str, Any]],
) -> dict[str, Any]:
    active_settings = settings or get_settings()
    state = _load_state_for_settings(active_settings)
    state["scheduler_last_sync"] = {
        "at": _now_iso(),
        "trigger_source": trigger_source,
        "execution_mode": execution_mode,
        "status": status,
        "jobs": synced_jobs,
    }
    _save_state_for_settings(active_settings, state)
    return state["scheduler_last_sync"]


def _persist_digest_run(
    settings: Settings,
    *,
    status: str,
    trigger_source: str,
    source: str,
    text: str,
    warnings: list[str],
    delivery_state: str,
    delivery_error: str = "",
    target_channel: str = "",
    target_chat_id: str = "",
) -> dict[str, Any]:
    state = _load_state_for_settings(settings)
    state["digest_last_run"] = {
        "at": _now_iso(),
        "status": status,
        "trigger": trigger_source,
        "source": source,
        "delivery_state": delivery_state,
        "delivery_error": delivery_error[:200],
        "target_channel": target_channel,
        "target_chat_id": target_chat_id,
        "warnings": warnings,
        "text_preview": text[:280],
    }
    _save_state_for_settings(settings, state)
    return state["digest_last_run"]


def _update_state(
    settings: Settings,
    *,
    status: str,
    provider: str,
    model: str,
    fallback_used: bool,
    trigger_source: str,
    job_name: str,
    duration_ms: int | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    state = _load_state_for_settings(settings)
    state.update(
        {
            "last_run_at": _now_iso(),
            "last_status": status,
            "last_provider": provider,
            "last_model": model,
            "last_fallback_used": fallback_used,
            "last_trigger": trigger_source,
            "last_job_name": job_name,
            "last_duration_ms": duration_ms if duration_ms is not None else state.get("last_duration_ms", 0),
            "last_error": error or "",
        }
    )
    _save_state_for_settings(settings, state)
    return state


def get_heartbeat_status(settings: Settings | None = None) -> dict[str, Any]:
    active_settings = settings or get_settings()
    state = _load_state_for_settings(active_settings)
    if not state:
        return {
            "last_run_at": "",
            "last_status": "never",
            "last_provider": "",
            "last_model": "",
            "last_fallback_used": False,
            "last_trigger": "",
            "last_job_name": "",
            "last_duration_ms": 0,
            "last_error": "",
        }
    return state


def get_digest_status(settings: Settings | None = None) -> dict[str, Any]:
    active_settings = settings or get_settings()
    config = get_scheduler_config(active_settings)
    state = _load_state_for_settings(active_settings)
    last = state.get("digest_last_run") or {}
    return {
        "enabled": bool(config["digest"]["enabled"]),
        "time": str(config["digest"]["time"]),
        "last_run_at": str(last.get("at") or ""),
        "last_status": str(last.get("status") or "never"),
        "last_trigger": str(last.get("trigger") or ""),
        "last_source": str(last.get("source") or ""),
        "last_delivery_state": str(last.get("delivery_state") or ""),
        "last_delivery_error": str(last.get("delivery_error") or ""),
        "last_target_channel": str(last.get("target_channel") or ""),
        "last_target_chat_id": str(last.get("target_chat_id") or ""),
        "last_warnings": list(last.get("warnings") or []),
    }


def get_digest_target(
    user_id: int | str,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    active_settings = settings or get_settings()
    state = _load_state_for_settings(active_settings)
    targets = state.get("digest_targets")
    if not isinstance(targets, dict):
        return None
    raw = targets.get(str(user_id))
    if not isinstance(raw, dict):
        return None
    return {
        "user_id": str(user_id),
        "channel": str(raw.get("channel") or "telegram"),
        "chat_id": str(raw.get("chat_id") or ""),
        "enabled": bool(raw.get("enabled", True)),
        "label": str(raw.get("label") or ""),
        "created_at": str(raw.get("created_at") or ""),
        "updated_at": str(raw.get("updated_at") or ""),
    }


def set_digest_target(
    user_id: int | str,
    *,
    channel: str,
    chat_id: int | str,
    enabled: bool = True,
    label: str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    active_settings = settings or get_settings()
    state = _load_state_for_settings(active_settings)
    targets = state.get("digest_targets")
    if not isinstance(targets, dict):
        targets = {}
    key = str(user_id)
    existing = targets.get(key)
    created_at = str(existing.get("created_at")) if isinstance(existing, dict) else _now_iso()
    targets[key] = {
        "channel": channel,
        "chat_id": str(chat_id),
        "enabled": bool(enabled),
        "label": label or "",
        "created_at": created_at,
        "updated_at": _now_iso(),
    }
    state["digest_targets"] = targets
    _save_state_for_settings(active_settings, state)
    return get_digest_target(user_id, settings=active_settings) or {}


def set_digest_target_enabled(
    user_id: int | str,
    *,
    enabled: bool,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    active_settings = settings or get_settings()
    current = get_digest_target(user_id, settings=active_settings)
    if not current:
        return None
    return set_digest_target(
        user_id,
        channel=current["channel"],
        chat_id=current["chat_id"],
        enabled=enabled,
        label=current.get("label") or None,
        settings=active_settings,
    )


def clear_digest_target(user_id: int | str, settings: Settings | None = None) -> bool:
    active_settings = settings or get_settings()
    state = _load_state_for_settings(active_settings)
    targets = state.get("digest_targets")
    if not isinstance(targets, dict):
        return False
    key = str(user_id)
    if key not in targets:
        return False
    del targets[key]
    state["digest_targets"] = targets
    _save_state_for_settings(active_settings, state)
    return True


def _resolve_digest_targets(
    *,
    settings: Settings,
    target_user_id: int | str | None = None,
) -> list[dict[str, Any]]:
    if target_user_id is not None:
        target = get_digest_target(target_user_id, settings=settings)
        if target and target.get("enabled"):
            return [target]
        return []
    state = _load_state_for_settings(settings)
    targets = state.get("digest_targets")
    if not isinstance(targets, dict):
        return []
    resolved: list[dict[str, Any]] = []
    for user_key, raw in targets.items():
        if not isinstance(raw, dict):
            continue
        if not bool(raw.get("enabled", True)):
            continue
        resolved.append(
            {
                "user_id": str(user_key),
                "channel": str(raw.get("channel") or "telegram"),
                "chat_id": str(raw.get("chat_id") or ""),
                "enabled": True,
                "label": str(raw.get("label") or ""),
            }
        )
    return resolved


async def run_heartbeat_tick(
    settings: Settings | None = None,
    *,
    trigger_source: str = "manual",
    job_name: str = JOB_HEARTBEAT_TICK,
) -> dict[str, Any]:
    active_settings = settings or get_settings()
    started = time.perf_counter()
    route = resolve_provider_for_task("heartbeat", active_settings)
    logger.info(
        "Heartbeat/Cron routing: provider_role=heartbeat trigger=%s job=%s provider=%s model=%s fallback_used=%s allowed=%s reason=%s",
        trigger_source,
        job_name,
        route.selected_provider,
        route.selected_model,
        route.fallback_used,
        route.allowed,
        route.reason or "",
    )
    if not route.allowed:
        duration_ms = int((time.perf_counter() - started) * 1000)
        state = _update_state(
            active_settings,
            status="degraded",
            provider=route.selected_provider,
            model=route.selected_model,
            fallback_used=route.fallback_used,
            trigger_source=trigger_source,
            job_name=job_name,
            duration_ms=duration_ms,
            error=route.reason or "provider_unavailable",
        )
        logger.warning(
            "Heartbeat/Cron result: provider_role=heartbeat trigger=%s job=%s status=degraded provider=%s duration_ms=%s reason=%s",
            trigger_source,
            job_name,
            route.selected_provider,
            duration_ms,
            route.reason or "provider_unavailable",
        )
        return {
            "ok": False,
            "status": "degraded",
            "provider": route.selected_provider,
            "model": route.selected_model,
            "fallback_used": route.fallback_used,
            "trigger": trigger_source,
            "job": job_name,
            "duration_ms": duration_ms,
            "actions": [],
            "logs": ["provider_unavailable"],
            "message": "Heartbeat utility provider is unavailable.",
            "state": state,
            "reason": route.reason or "",
        }

    actions: list[dict[str, Any]] = []
    logs: list[str] = []

    hb_result = call_sidecar_action(
        "heartbeat_tick",
        {
            "event_type": "heartbeat_tick",
            "event_source": "openclaw",
            "event_details": {
                "runner": "openclaw_heartbeat",
                "trigger_source": trigger_source,
                "job_name": job_name,
                "provider": route.selected_provider,
                "model": route.selected_model,
                "fallback_used": route.fallback_used,
            },
        },
        user_id="system",
        source="openclaw",
    )
    actions.append({"action": "heartbeat_tick", "status": hb_result.status})
    logs.append(f"heartbeat_tick={hb_result.status}")

    reminder_result = call_sidecar_action(
        "reminder_trigger_due",
        {},
        user_id="system",
        source="openclaw",
    )
    actions.append({"action": "reminder_trigger_due", "status": reminder_result.status})
    logs.append(f"reminder_trigger_due={reminder_result.status}")

    digest_result = call_sidecar_action(
        "digest_generate",
        {"digest_type": "system_state"},
        user_id="system",
        source="openclaw",
    )
    actions.append({"action": "digest_generate", "status": digest_result.status})
    logs.append(f"digest_generate={digest_result.status}")

    status = "ok" if all(item["status"] == "ok" for item in actions) else "degraded"
    error = "" if status == "ok" else "one_or_more_actions_failed"
    duration_ms = int((time.perf_counter() - started) * 1000)
    state = _update_state(
        active_settings,
        status=status,
        provider=route.selected_provider,
        model=route.selected_model,
        fallback_used=route.fallback_used,
        trigger_source=trigger_source,
        job_name=job_name,
        duration_ms=duration_ms,
        error=error or None,
    )
    logger.info(
        "Heartbeat/Cron result: provider_role=heartbeat trigger=%s job=%s status=%s provider=%s duration_ms=%s",
        trigger_source,
        job_name,
        status,
        route.selected_provider,
        duration_ms,
    )
    return {
        "ok": status == "ok",
        "status": status,
        "provider": route.selected_provider,
        "model": route.selected_model,
        "fallback_used": route.fallback_used,
        "trigger": trigger_source,
        "job": job_name,
        "duration_ms": duration_ms,
        "actions": actions,
        "logs": logs,
        "message": f"Heartbeat tick completed: {status}.",
        "state": state,
    }


def build_daily_digest_text(settings: Settings | None = None) -> dict[str, Any]:
    active_settings = settings or get_settings()
    warnings: list[str] = []
    sections_present: list[str] = []

    planned_lines: list[str] = []
    tasks_lines: list[str] = []
    recent_lines: list[str] = []

    plans = call_sidecar_action(
        "event_list",
        {"status": "planned", "limit": 3, "offset": 0},
        user_id="system",
        source="openclaw",
    )
    if plans.status == "ok":
        for item in (plans.data or {}).get("events", [])[:3]:
            planned_lines.append(f"- {str(item.get('title') or '').strip()}")
    else:
        warnings.append("plans_unavailable")
    if planned_lines:
        sections_present.append("plans")

    tasks = call_sidecar_action(
        "task_list",
        {"project_id": None, "status": "open", "limit": 3, "offset": 0},
        user_id="system",
        source="openclaw",
    )
    if tasks.status == "ok":
        for item in (tasks.data or {}).get("tasks", [])[:3]:
            title = str(item.get("title") or "").strip() or f"task#{item.get('id')}"
            tasks_lines.append(f"- {title}")
    else:
        warnings.append("tasks_unavailable")
    if tasks_lines:
        sections_present.append("tasks")

    hb = get_heartbeat_status(active_settings)
    hb_line = (
        f"Р С—Р С•РЎРѓР В»Р ВµР Т‘Р Р…Р С‘Р в„– Р В·Р В°Р С—РЎС“РЎРѓР С”={hb.get('last_run_at') or 'Р Р…Р ВµРЎвЂљ'}; "
        f"РЎРѓРЎвЂљР В°РЎвЂљРЎС“РЎРѓ={hb.get('last_status') or 'never'}; "
        f"Р С—РЎР‚Р С•Р Р†Р В°Р в„–Р Т‘Р ВµРЎР‚={hb.get('last_provider') or 'n/a'}"
    )
    sections_present.append("heartbeat_snapshot")

    now_utc = datetime.now(timezone.utc)
    for key, label in (
        ("last_run_at", "heartbeat"),
        ("last_run_at", "digest"),
    ):
        raw = hb.get(key) if label == "heartbeat" else (get_digest_status(active_settings).get("last_run_at") or "")
        if not raw:
            continue
        try:
            ts = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            if (now_utc - ts).total_seconds() <= 86400:
                recent_lines.append(f"- {label}: {str(raw)}")
        except ValueError:
            continue
    scheduler_sync = (_load_state_for_settings(active_settings).get("scheduler_last_sync") or {}).get("at")
    if scheduler_sync:
        recent_lines.append(f"- scheduler_sync: {scheduler_sync}")
    if recent_lines:
        sections_present.append("recent_actions")

    if planned_lines:
        next_line = "Р В§РЎвЂљР С• Р Т‘Р В°Р В»РЎРЉРЎв‚¬Р Вµ: Р Р†РЎвЂ№Р В±Р ВµРЎР‚Р С‘ Р С•Р Т‘Р С‘Р Р… Р С—Р В»Р В°Р Р… Р С‘ Р Р…Р В°РЎвЂЎР Р…Р С‘ Р С—Р ВµРЎР‚Р Р†РЎвЂ№Р в„– РЎв‚¬Р В°Р С–."
    elif tasks_lines:
        next_line = "Р В§РЎвЂљР С• Р Т‘Р В°Р В»РЎРЉРЎв‚¬Р Вµ: Р В·Р В°Р С”РЎР‚Р С•Р в„– Р С•Р Т‘Р Р…РЎС“ Р С•РЎвЂљР С”РЎР‚РЎвЂ№РЎвЂљРЎС“РЎР‹ Р В·Р В°Р Т‘Р В°РЎвЂЎРЎС“."
    else:
        next_line = "Р В§РЎвЂљР С• Р Т‘Р В°Р В»РЎРЉРЎв‚¬Р Вµ: Р Т‘Р С•Р В±Р В°Р Р†РЎРЉ Р Р…Р С•Р Р†РЎвЂ№Р в„– Р С—Р В»Р В°Р Р… РЎвЂЎР ВµРЎР‚Р ВµР В· /plan add <title>."
    sections_present.append("what_next")

    lines = [
        "Р вЂўР В¶Р ВµР Т‘Р Р…Р ВµР Р†Р Р…РЎвЂ№Р в„– Р Т‘Р В°Р в„–Р Т‘Р В¶Р ВµРЎРѓРЎвЂљ",
        "",
        "Р СџР В»Р В°Р Р…РЎвЂ№:",
    ]
    lines.extend(planned_lines or ["- Р СњР ВµРЎвЂљ Р Т‘Р В°Р Р…Р Р…РЎвЂ№РЎвЂ¦"])
    lines.extend(["", "Р вЂ”Р В°Р Т‘Р В°РЎвЂЎР С‘:"])
    lines.extend(tasks_lines or ["- Р СњР ВµРЎвЂљ Р Т‘Р В°Р Р…Р Р…РЎвЂ№РЎвЂ¦"])
    lines.extend(["", "Р РЋР С•РЎРѓРЎвЂљР С•РЎРЏР Р…Р С‘Р Вµ heartbeat:", hb_line, "", "Р СџР С•РЎРѓР В»Р ВµР Т‘Р Р…Р С‘Р Вµ Р Т‘Р ВµР в„–РЎРѓРЎвЂљР Р†Р С‘РЎРЏ (24РЎвЂЎ):"])
    lines.extend(recent_lines or ["- Р СњР ВµРЎвЂљ Р Т‘Р В°Р Р…Р Р…РЎвЂ№РЎвЂ¦"])
    lines.extend(["", next_line])

    text = "\n".join(lines).strip()
    return {
        "ok": True,
        "text": text,
        "sections_present": sections_present,
        "warnings": warnings,
    }


async def run_digest_daily(
    settings: Settings | None = None,
    *,
    trigger_source: str = "manual",
    job_name: str = JOB_DIGEST_DAILY,
    persist: bool = True,
    preview_only: bool = False,
    target_user_id: int | str | None = None,
    deliver_to_target: bool = True,
) -> dict[str, Any]:
    active_settings = settings or get_settings()
    started = time.perf_counter()
    route = resolve_provider_for_task("cron", active_settings)
    if route.task_type != TASK_CRON_SUMMARY:
        logger.warning(
            "Digest route guard failed: expected=%s got=%s trigger=%s",
            TASK_CRON_SUMMARY,
            route.task_type,
            trigger_source,
        )
        return {
            "ok": False,
            "status": "error",
            "provider_role": "cron",
            "trigger": trigger_source,
            "job": job_name,
            "message": "Р СљР В°РЎР‚РЎв‚¬РЎР‚РЎС“РЎвЂљ digest Р Р…Р В°РЎРѓРЎвЂљРЎР‚Р С•Р ВµР Р… Р Р…Р ВµР Р†Р ВµРЎР‚Р Р…Р С•.",
            "warnings": ["route_guard_failed"],
        }
    trigger_kind = "cron" if trigger_source == "scheduled_openclaw" else "manual"
    logger.info(
        "Heartbeat/Cron routing: trigger=%s trigger_source=%s provider_role=cron job=%s provider=%s model=%s fallback_used=%s allowed=%s reason=%s",
        trigger_kind,
        trigger_source,
        job_name,
        route.selected_provider,
        route.selected_model,
        route.fallback_used,
        route.allowed,
        route.reason or "",
    )
    if not route.allowed:
        duration_ms = int((time.perf_counter() - started) * 1000)
        state = _update_state(
            active_settings,
            status="degraded",
            provider=route.selected_provider,
            model=route.selected_model,
            fallback_used=route.fallback_used,
            trigger_source=trigger_source,
            job_name=job_name,
            duration_ms=duration_ms,
            error=route.reason or "provider_unavailable",
        )
        logger.warning(
            "Heartbeat/Cron result: provider_role=cron trigger=%s job=%s status=degraded provider=%s duration_ms=%s reason=%s",
            trigger_source,
            job_name,
            route.selected_provider,
            duration_ms,
            route.reason or "provider_unavailable",
        )
        return {
            "ok": False,
            "status": "degraded",
            "provider_role": "cron",
            "provider": route.selected_provider,
            "model": route.selected_model,
            "fallback_used": route.fallback_used,
            "trigger": trigger_source,
            "job": job_name,
            "duration_ms": duration_ms,
            "actions": [],
            "logs": ["provider_unavailable"],
            "message": "Cron utility provider is unavailable.",
            "state": state,
            "reason": route.reason or "",
        }

    digest_build = build_daily_digest_text(active_settings)
    digest_text = str(digest_build.get("text") or "").strip()
    warnings = list(digest_build.get("warnings") or [])
    status = "ok" if digest_build.get("ok") else "degraded"
    error = "" if status == "ok" else "digest_build_failed"
    if not digest_text:
        status = "degraded"
        warnings.append("digest_text_empty")
        digest_text = "Р вЂќР В°Р в„–Р Т‘Р В¶Р ВµРЎРѓРЎвЂљ Р С—Р С•Р С”Р В° Р Р…Р ВµР Т‘Р С•РЎРѓРЎвЂљРЎС“Р С—Р ВµР Р…. Р СџР С•Р С—РЎР‚Р С•Р В±РЎС“Р в„–РЎвЂљР Вµ Р С—Р С•Р В·Р В¶Р Вµ."
        error = "digest_text_empty"
    duration_ms = int((time.perf_counter() - started) * 1000)
    state = _update_state(
        active_settings,
        status=status,
        provider=route.selected_provider,
        model=route.selected_model,
        fallback_used=route.fallback_used,
        trigger_source=trigger_source,
        job_name=job_name,
        duration_ms=duration_ms,
        error=error or None,
    )
    delivery = "deferred" if preview_only else "stub_fallback"
    delivery_error = ""
    target_channel = ""
    target_chat_id = ""
    target_resolved = False
    if not preview_only and deliver_to_target:
        targets = _resolve_digest_targets(settings=active_settings, target_user_id=target_user_id)
        if not targets:
            delivery = "no_target"
            target_resolved = False
            logger.warning(
                "Digest delivery skipped: trigger=%s trigger_source=%s provider_role=cron job=%s delivery_state=no_target target_resolved=false",
                trigger_kind,
                trigger_source,
                job_name,
            )
        else:
            target_resolved = True
            outbound = build_openclaw_outbound(settings=active_settings)
            delivery_states: list[str] = []
            for target in targets:
                send_result = outbound.send_digest(
                    channel=str(target.get("channel") or "telegram"),
                    target=str(target.get("chat_id") or ""),
                    text=digest_text,
                    trigger=trigger_kind,
                    provider_role="cron",
                )
                target_channel = str(send_result.channel or "")
                target_chat_id = str(send_result.target or "")
                state_value = str(send_result.delivery_state or "failed")
                delivery_states.append(state_value)
                if not send_result.ok:
                    delivery_error = str(send_result.error or "")
            if "failed" in delivery_states:
                delivery = "failed"
            elif "deferred" in delivery_states:
                delivery = "deferred"
            elif "sent" in delivery_states:
                delivery = "sent"
            else:
                delivery = "deferred"
            if delivery == "failed":
                logger.warning(
                    "Digest delivery failed: trigger=%s trigger_source=%s provider_role=cron job=%s delivery_state=failed target_resolved=true error=%s",
                    trigger_kind,
                    trigger_source,
                    job_name,
                    delivery_error[:120],
                )
    elif preview_only:
        target_resolved = False
    else:
        delivery = "deferred"
        target_resolved = False
    if persist:
        _persist_digest_run(
            active_settings,
            status=status,
            trigger_source=trigger_source,
            source=trigger_source,
            text=digest_text,
            warnings=warnings,
            delivery_state=delivery,
            delivery_error=delivery_error,
            target_channel=target_channel,
            target_chat_id=target_chat_id,
        )
    logger.info(
        "Heartbeat/Cron result: trigger=%s trigger_source=%s provider_role=cron job=%s status=%s provider=%s duration_ms=%s delivery_state=%s target_resolved=%s",
        trigger_kind,
        trigger_source,
        job_name,
        status,
        route.selected_provider,
        duration_ms,
        delivery,
        target_resolved,
    )
    return {
        "ok": status == "ok",
        "status": status,
        "provider_role": "cron",
        "provider": route.selected_provider,
        "model": route.selected_model,
        "fallback_used": route.fallback_used,
        "trigger_kind": trigger_kind,
        "trigger": trigger_source,
        "job": job_name,
        "duration_ms": duration_ms,
        "text": digest_text,
        "sections_present": list(digest_build.get("sections_present") or []),
        "warnings": warnings,
        "target_resolved": target_resolved,
        "target_channel": target_channel,
        "target_chat_id": target_chat_id,
        "delivery_error": delivery_error,
        "actions": [{"action": "digest_build", "status": status}],
        "logs": [f"digest_build={status}", f"delivery={delivery}"],
        "message": f"Daily digest run completed: {status}.",
        "delivery": delivery,
        "state": state,
    }


def run_heartbeat_tick_sync(
    settings: Settings | None = None,
    *,
    trigger_source: str = "manual",
    job_name: str = JOB_HEARTBEAT_TICK,
) -> dict[str, Any]:
    return asyncio.run(
        run_heartbeat_tick(
            settings=settings,
            trigger_source=trigger_source,
            job_name=job_name,
        )
    )


def run_digest_daily_sync(
    settings: Settings | None = None,
    *,
    trigger_source: str = "manual",
    job_name: str = JOB_DIGEST_DAILY,
    persist: bool = True,
    preview_only: bool = False,
    target_user_id: int | str | None = None,
    deliver_to_target: bool = True,
) -> dict[str, Any]:
    return asyncio.run(
        run_digest_daily(
            settings=settings,
            trigger_source=trigger_source,
            job_name=job_name,
            persist=persist,
            preview_only=preview_only,
            target_user_id=target_user_id,
            deliver_to_target=deliver_to_target,
        )
    )


def _job_registry() -> dict[str, Callable[[Settings | None, str, str, int | str | None], dict[str, Any]]]:
    return {
        JOB_HEARTBEAT_TICK: lambda settings, trigger_source, job_name, user_id: run_heartbeat_tick_sync(
            settings=settings,
            trigger_source=trigger_source,
            job_name=job_name,
        ),
        JOB_DIGEST_DAILY: lambda settings, trigger_source, job_name, user_id: run_digest_daily_sync(
            settings=settings,
            trigger_source=trigger_source,
            job_name=job_name,
            target_user_id=user_id,
            deliver_to_target=True,
        ),
    }


def list_registered_jobs(settings: Settings | None = None) -> list[dict[str, Any]]:
    specs = build_job_specs(settings)
    return [item for item in specs if item["name"] in _job_registry()]


def list_cron_jobs(*, include_unsafe: bool = False, settings: Settings | None = None) -> list[str]:
    _ = include_unsafe
    return [item["name"] for item in list_registered_jobs(settings=settings)]


def run_registered_job(
    job_name: str,
    settings: Settings | None = None,
    *,
    trigger_source: str,
    user_id: int | str | None = None,
) -> dict[str, Any]:
    registry = _job_registry()
    handler = registry.get(job_name)
    if handler is None:
        return {
            "ok": False,
            "status": "error",
            "error": "job_not_registered",
            "job": job_name,
            "trigger": trigger_source,
        }
    return handler(settings, trigger_source, job_name, user_id)


def run_cron_job(
    job_name: str,
    settings: Settings | None = None,
    *,
    user_id: int | str | None = None,
) -> dict[str, Any]:
    return run_registered_job(
        job_name,
        settings=settings,
        trigger_source="manual_bridge",
        user_id=user_id,
    )


def run_scheduled_job(
    job_name: str,
    settings: Settings | None = None,
    *,
    user_id: int | str | None = None,
) -> dict[str, Any]:
    return run_registered_job(
        job_name,
        settings=settings,
        trigger_source="scheduled_openclaw",
        user_id=user_id,
    )
