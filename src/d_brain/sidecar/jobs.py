"""Job definitions for the sidecar scheduler."""

from __future__ import annotations

import logging

from d_brain.config import Settings, get_settings

from .plans import trigger_due_reminders
from .news import generate_manual_briefing
from .store import SQLiteStore, utc_now
from d_brain.bot.formatters import (
    format_news_briefing,
    format_reminder_delivery,
)
from d_brain.services.telegram_delivery import (
    send_to_allowed_users,
    send_telegram_message,
)
from d_brain.services.db_backup import run_backup
from d_brain.services.model_routing import (
    TASK_CRON_SUMMARY,
    TASK_HEARTBEAT,
    resolve_route,
)

logger = logging.getLogger(__name__)

def noop_job() -> None:
    """No-op job for scheduler smoke tests."""
    return None


def reminder_tick_job() -> None:
    """Trigger due reminders once."""
    settings = get_settings()
    store = SQLiteStore(settings.db_path)
    trigger_due_reminders(store)


def _log_reminder_delivery(
    store: SQLiteStore,
    reminders: list[dict[str, object]],
    chat_id: int | None,
    mode: str,
    status: str,
    message_id: int | None,
    error: str | None,
) -> None:
    settings = get_settings()
    route = resolve_route(TASK_HEARTBEAT, settings)
    logger.info(
        "Model routing: channel=job action=reminder_delivery task_type=%s provider=%s model=%s fallback_used=%s allowed=%s reason=%s",
        route.task_type,
        route.selected_provider,
        route.selected_model,
        route.fallback_used,
        route.allowed,
        route.reason or "",
    )
    for reminder in reminders:
        store.create_heartbeat_log(
            event_type="reminder_delivery",
            event_source="telegram",
            event_details={
                "mode": mode,
                "chat_id": chat_id,
                "status": status,
                "reminder_id": reminder.get("reminder_id"),
                "event_id": reminder.get("event_id"),
                "message_id": message_id,
                "error": error,
                "model_routing": route.to_diagnostics(),
            },
        )


def deliver_due_reminders(
    store: SQLiteStore,
    settings: Settings,
    chat_ids: list[int],
    mode: str,
) -> dict[str, object]:
    now_iso = utc_now()
    due = store.list_due_reminders_with_events(now_iso)
    if not due:
        return {"attempted": 0, "delivered": 0, "skipped": True}

    if not chat_ids:
        _log_reminder_delivery(
            store,
            due,
            chat_id=None,
            mode=mode,
            status="skipped",
            message_id=None,
            error="No chat_ids configured",
        )
        return {"attempted": len(due), "delivered": 0, "skipped": True}

    message = format_reminder_delivery(due, now_iso)
    any_sent = False
    for chat_id in chat_ids:
        result = send_telegram_message(
            settings.telegram_bot_token,
            int(chat_id),
            message,
            parse_mode="HTML",
        )
        if result.ok:
            any_sent = True
        _log_reminder_delivery(
            store,
            due,
            chat_id=int(chat_id),
            mode=mode,
            status="sent" if result.ok else "failed",
            message_id=result.message_id,
            error=result.error,
        )

    if any_sent:
        for reminder in due:
            store.mark_reminder_triggered(int(reminder["reminder_id"]))

    return {
        "attempted": len(due),
        "delivered": len(due) if any_sent else 0,
        "sent": any_sent,
        "chat_ids": chat_ids,
    }


def reminder_delivery_telegram_job() -> None:
    """Deliver due reminders to Telegram via allowed user list."""
    settings = get_settings()
    store = SQLiteStore(settings.db_path)
    deliver_due_reminders(
        store,
        settings,
        list(settings.allowed_user_ids),
        mode="scheduler",
    )


def news_briefing_generate_daily_job() -> None:
    """Generate a daily news briefing using existing pipeline."""
    settings = get_settings()
    route = resolve_route(TASK_CRON_SUMMARY, settings)
    logger.info(
        "Model routing: channel=job action=news_briefing_generate_daily task_type=%s provider=%s model=%s fallback_used=%s allowed=%s reason=%s",
        route.task_type,
        route.selected_provider,
        route.selected_model,
        route.fallback_used,
        route.allowed,
        route.reason or "",
    )
    if not route.allowed:
        logger.warning(
            "Skipping daily news briefing generation: task_type=%s provider=%s model=%s reason=%s",
            route.task_type,
            route.selected_provider,
            route.selected_model,
            route.reason or "",
        )
        return
    store = SQLiteStore(settings.db_path)
    logger.info("Generating daily news briefing...")
    generate_manual_briefing(
        store,
        section_id=None,
        source_id=None,
        limit=50,
        target_count=5,
        briefing_mode="daily",
    )
    briefing = store.get_latest_briefing()
    items = (briefing.get("items") or []) if briefing else []
    logger.info("Daily news briefing generated. briefing_id=%s items=%d", briefing.get("id") if briefing else None, len(items))


def news_briefing_deliver_telegram_job() -> None:
    """Deliver the latest news briefing to Telegram."""
    settings = get_settings()
    store = SQLiteStore(settings.db_path)
    route = resolve_route(TASK_HEARTBEAT, settings)
    logger.info(
        "Model routing: channel=job action=news_briefing_deliver_telegram task_type=%s provider=%s model=%s fallback_used=%s allowed=%s reason=%s",
        route.task_type,
        route.selected_provider,
        route.selected_model,
        route.fallback_used,
        route.allowed,
        route.reason or "",
    )
    briefing = store.get_latest_briefing()
    message = format_news_briefing(briefing, max_items=5)
    logger.info("Delivering latest news briefing to Telegram. briefing_id=%s", briefing.get("id") if briefing else None)
    results = send_to_allowed_users(settings, message, parse_mode="HTML")
    if not results:
        logger.warning("News delivery skipped. No allowed_user_ids configured.")
        store.create_heartbeat_log(
            event_type="news_delivery",
            event_source="telegram",
            event_details={
                "briefing_id": briefing.get("id"),
                "status": "skipped",
                "error": "No allowed_user_ids configured",
                "model_routing": route.to_diagnostics(),
            },
        )
    for result in results:
        if result.ok:
            logger.info("News delivered. chat_id=%s message_id=%s", result.chat_id, result.message_id)
        else:
            logger.warning("News delivery failed. chat_id=%s error=%s", result.chat_id, result.error)
        store.create_heartbeat_log(
            event_type="news_delivery",
            event_source="telegram",
            event_details={
                "briefing_id": briefing.get("id"),
                "chat_id": result.chat_id,
                "status": "sent" if result.ok else "failed",
                "message_id": result.message_id,
                "error": result.error,
                "model_routing": route.to_diagnostics(),
            },
        )


def db_backup_weekly_job() -> None:
    """Create a weekly SQLite backup and optional project snapshot."""
    settings = get_settings()
    run_backup(settings, project_root=None)
