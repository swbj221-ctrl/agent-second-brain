"""Job definitions for the sidecar scheduler."""

from __future__ import annotations

from d_brain.config import get_settings

from .plans import trigger_due_reminders
from .news import generate_manual_briefing
from .store import SQLiteStore
from d_brain.bot.formatters import format_news_briefing
from d_brain.services.telegram_delivery import send_to_allowed_users


def noop_job() -> None:
    """No-op job for scheduler smoke tests."""
    return None


def reminder_tick_job() -> None:
    """Trigger due reminders once."""
    settings = get_settings()
    store = SQLiteStore(settings.db_path)
    trigger_due_reminders(store)


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
