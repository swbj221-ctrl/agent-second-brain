"""Job definitions for the sidecar scheduler."""

from __future__ import annotations

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
    store = SQLiteStore(settings.db_path)
    generate_manual_briefing(
        store,
        section_id=None,
        source_id=None,
        limit=50,
        target_count=5,
        briefing_mode="daily",
    )


def news_briefing_deliver_telegram_job() -> None:
    """Deliver the latest news briefing to Telegram."""
    settings = get_settings()
    store = SQLiteStore(settings.db_path)
    briefing = store.get_latest_briefing()
    message = format_news_briefing(briefing, max_items=5)
    results = send_to_allowed_users(settings, message, parse_mode="HTML")
    if not results:
        store.create_heartbeat_log(
            event_type="news_delivery",
            event_source="telegram",
            event_details={
                "briefing_id": briefing.get("id"),
                "status": "skipped",
                "error": "No allowed_user_ids configured",
            },
        )
    for result in results:
        store.create_heartbeat_log(
            event_type="news_delivery",
            event_source="telegram",
            event_details={
                "briefing_id": briefing.get("id"),
                "chat_id": result.chat_id,
                "status": "sent" if result.ok else "failed",
                "message_id": result.message_id,
                "error": result.error,
            },
        )


def db_backup_weekly_job() -> None:
    """Create a weekly SQLite backup and optional project snapshot."""
    settings = get_settings()
    run_backup(settings, project_root=None)
