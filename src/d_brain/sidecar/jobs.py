"""Job definitions for the sidecar scheduler."""

from __future__ import annotations

from d_brain.config import get_settings

from .plans import trigger_due_reminders
from .store import SQLiteStore


def noop_job() -> None:
    """No-op job for scheduler smoke tests."""
    return None


def reminder_tick_job() -> None:
    """Trigger due reminders once."""
    settings = get_settings()
    store = SQLiteStore(settings.db_path)
    trigger_due_reminders(store)
